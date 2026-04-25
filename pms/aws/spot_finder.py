"""SpotFinder - Cost-effective spot instance discovery."""

from __future__ import annotations

import asyncio
import fnmatch
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pms.aws.models import SpotOption, SpotQuery

if TYPE_CHECKING:
    from mypy_boto3_ec2 import EC2Client
else:
    EC2Client = Any


# Instance type specifications (subset of common types)
# Format: (vcpus, memory_gb, architecture)
INSTANCE_SPECS: dict[str, tuple[int, float, str]] = {
    # T3 family (burstable, x86_64)
    "t3.micro": (2, 1.0, "x86_64"),
    "t3.small": (2, 2.0, "x86_64"),
    "t3.medium": (2, 4.0, "x86_64"),
    "t3.large": (2, 8.0, "x86_64"),
    "t3.xlarge": (4, 16.0, "x86_64"),
    "t3.2xlarge": (8, 32.0, "x86_64"),
    # T3a family (AMD, x86_64)
    "t3a.micro": (2, 1.0, "x86_64"),
    "t3a.small": (2, 2.0, "x86_64"),
    "t3a.medium": (2, 4.0, "x86_64"),
    "t3a.large": (2, 8.0, "x86_64"),
    "t3a.xlarge": (4, 16.0, "x86_64"),
    "t3a.2xlarge": (8, 32.0, "x86_64"),
    # M5 family (general purpose, x86_64)
    "m5.large": (2, 8.0, "x86_64"),
    "m5.xlarge": (4, 16.0, "x86_64"),
    "m5.2xlarge": (8, 32.0, "x86_64"),
    # M5a family (AMD, x86_64)
    "m5a.large": (2, 8.0, "x86_64"),
    "m5a.xlarge": (4, 16.0, "x86_64"),
    "m5a.2xlarge": (8, 32.0, "x86_64"),
    # C5 family (compute optimized, x86_64)
    "c5.large": (2, 4.0, "x86_64"),
    "c5.xlarge": (4, 8.0, "x86_64"),
    "c5.2xlarge": (8, 16.0, "x86_64"),
    # C5a family (AMD, x86_64)
    "c5a.large": (2, 4.0, "x86_64"),
    "c5a.xlarge": (4, 8.0, "x86_64"),
    "c5a.2xlarge": (8, 16.0, "x86_64"),
    # T4g family (Graviton, arm64)
    "t4g.micro": (2, 1.0, "arm64"),
    "t4g.small": (2, 2.0, "arm64"),
    "t4g.medium": (2, 4.0, "arm64"),
    "t4g.large": (2, 8.0, "arm64"),
    "t4g.xlarge": (4, 16.0, "arm64"),
    "t4g.2xlarge": (8, 32.0, "arm64"),
    # M6g family (Graviton, arm64)
    "m6g.medium": (1, 4.0, "arm64"),
    "m6g.large": (2, 8.0, "arm64"),
    "m6g.xlarge": (4, 16.0, "arm64"),
    "m6g.2xlarge": (8, 32.0, "arm64"),
    # C6g family (Graviton compute, arm64)
    "c6g.medium": (1, 2.0, "arm64"),
    "c6g.large": (2, 4.0, "arm64"),
    "c6g.xlarge": (4, 8.0, "arm64"),
    "c6g.2xlarge": (8, 16.0, "arm64"),
}

# Approximate interruption rates by instance family
# Based on historical data from AWS Spot Instance Advisor
# These are estimates - actual rates vary by AZ and time
INTERRUPTION_RATES: dict[str, float] = {
    "t3": 0.05,
    "t3a": 0.08,
    "t4g": 0.03,
    "m5": 0.10,
    "m5a": 0.12,
    "m6g": 0.05,
    "c5": 0.08,
    "c5a": 0.10,
    "c6g": 0.04,
}


@dataclass
class SpotPriceResult:
    """Result of a spot price query."""

    instance_type: str
    availability_zone: str
    price: Decimal
    timestamp: datetime


class SpotFinder:
    """Find cost-effective spot instances for testing."""

    def __init__(self, ec2_clients: dict[str, EC2Client]) -> None:
        """Initialize SpotFinder with EC2 clients per region.

        Args:
            ec2_clients: Dict mapping region name to EC2 client
        """
        self._ec2_clients = ec2_clients

    @classmethod
    def create(cls, boto_session: Any, regions: tuple[str, ...]) -> SpotFinder:
        """Create SpotFinder with clients for specified regions.

        Args:
            boto_session: Boto3 session
            regions: Regions to query

        Returns:
            Configured SpotFinder instance
        """

        clients = {
            region: boto_session.client("ec2", region_name=region) for region in regions
        }
        return cls(clients)

    async def find_best_options(
        self,
        query: SpotQuery,
        limit: int = 5,
    ) -> list[SpotOption]:
        """Find the best spot instance options based on query criteria.

        Scoring considers:
        - Price per vCPU-hour (lower is better)
        - Interruption rate (lower is better if prefer_low_interruption)
        - Memory/vCPU ratio for the workload

        Args:
            query: Query parameters
            limit: Maximum number of options to return

        Returns:
            List of SpotOption sorted by score (best first)
        """
        # Get eligible instance types
        eligible_types = self._get_eligible_types(query)
        if not eligible_types:
            return []

        # Fetch spot prices for all regions in parallel
        all_prices: list[SpotPriceResult] = []
        tasks = []
        for region in query.regions:
            if region in self._ec2_clients:
                tasks.append(self._get_spot_prices(region, eligible_types))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                all_prices.extend(result)

        # Filter by max price
        valid_prices = [p for p in all_prices if p.price <= query.max_price_per_hour]

        # Score and sort options
        options = []
        for price_result in valid_prices:
            spec = INSTANCE_SPECS.get(price_result.instance_type)
            if not spec:
                continue

            vcpus, memory_gb, _ = spec
            interruption_rate = self._get_interruption_rate(price_result.instance_type)

            # Calculate score (higher is better)
            # Base: inverse of price per vCPU
            price_per_vcpu = float(price_result.price) / vcpus
            price_score = 1.0 / (price_per_vcpu + 0.001)  # Avoid division by zero

            # Memory bonus for workloads needing memory
            memory_ratio = memory_gb / vcpus
            memory_score = min(memory_ratio / 4.0, 1.0)  # Normalize to 0-1

            # Interruption penalty
            interruption_score = (
                1.0 - interruption_rate if query.prefer_low_interruption else 0.5
            )

            # Combined score
            score = price_score * 0.5 + memory_score * 0.2 + interruption_score * 0.3

            options.append(
                SpotOption(
                    instance_type=price_result.instance_type,
                    availability_zone=price_result.availability_zone,
                    current_price=price_result.price,
                    interruption_rate=interruption_rate,
                    vcpus=vcpus,
                    memory_gb=memory_gb,
                    score=round(score, 3),
                )
            )

        # Sort by score (highest first) and return top N
        options.sort(key=lambda x: x.score, reverse=True)
        return options[:limit]

    async def get_current_price(
        self,
        instance_type: str,
        availability_zone: str,
    ) -> Decimal | None:
        """Get current spot price for a specific instance type and AZ.

        Args:
            instance_type: EC2 instance type
            availability_zone: Availability zone (e.g., "us-east-1a")

        Returns:
            Current spot price in USD/hour, or None if not available
        """
        # Extract region from AZ
        region = availability_zone[:-1]  # e.g., "us-east-1a" -> "us-east-1"

        if region not in self._ec2_clients:
            return None

        prices = await self._get_spot_prices(region, [instance_type])
        for price in prices:
            if price.availability_zone == availability_zone:
                return price.price

        return None

    def get_instance_specs(self, instance_type: str) -> tuple[int, float, str] | None:
        """Get specifications for an instance type.

        Args:
            instance_type: EC2 instance type

        Returns:
            Tuple of (vcpus, memory_gb, architecture) or None if unknown
        """
        return INSTANCE_SPECS.get(instance_type)

    def _get_eligible_types(self, query: SpotQuery) -> list[str]:
        """Get instance types that meet query requirements."""
        eligible = []
        for instance_type, (vcpus, memory_gb, arch) in INSTANCE_SPECS.items():
            # Check minimum requirements
            if vcpus < query.min_vcpus:
                continue
            if memory_gb < query.min_memory_gb:
                continue
            if arch != query.architecture:
                continue

            # Check exclusion patterns
            excluded = False
            for pattern in query.exclude_instance_types:
                if fnmatch.fnmatch(instance_type, pattern):
                    excluded = True
                    break
            if excluded:
                continue

            eligible.append(instance_type)

        return eligible

    async def _get_spot_prices(
        self,
        region: str,
        instance_types: list[str],
    ) -> list[SpotPriceResult]:
        """Fetch current spot prices from AWS.

        Args:
            region: AWS region
            instance_types: Instance types to query

        Returns:
            List of spot price results
        """
        client = self._ec2_clients[region]

        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.describe_spot_price_history(
                InstanceTypes=instance_types,  # type: ignore[arg-type]
                ProductDescriptions=["Linux/UNIX"],
                StartTime=datetime.now(UTC) - timedelta(hours=1),
                MaxResults=100,
            ),
        )

        # Parse results - keep only the most recent price per AZ/type combo
        latest: dict[tuple[str, str], SpotPriceResult] = {}
        for item in response.get("SpotPriceHistory", []):
            key = (item["InstanceType"], item["AvailabilityZone"])
            price = Decimal(item["SpotPrice"])
            timestamp = item["Timestamp"]

            if key not in latest or timestamp > latest[key].timestamp:
                latest[key] = SpotPriceResult(
                    instance_type=item["InstanceType"],
                    availability_zone=item["AvailabilityZone"],
                    price=price,
                    timestamp=timestamp,
                )

        return list(latest.values())

    def _get_interruption_rate(self, instance_type: str) -> float:
        """Get estimated interruption rate for an instance type.

        Args:
            instance_type: EC2 instance type

        Returns:
            Estimated interruption rate (0-1)
        """
        # Extract family from instance type (e.g., "t3.medium" -> "t3")
        match = re.match(r"([a-z0-9]+)\.", instance_type)
        if match:
            family = match.group(1)
            return INTERRUPTION_RATES.get(family, 0.15)  # Default 15%
        return 0.15
