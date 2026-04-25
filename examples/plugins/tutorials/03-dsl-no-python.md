# Tutorial 3: DSL-Only Plugins (No Python Required)

**Time:** 10 minutes
**Level:** Beginner-Intermediate
**What you'll learn:** Create tools using the declarative DSL - no Python needed

---

## The Scenario

You want to create some quick utility tools but don't want to write Python code. The PMS DSL (Domain-Specific Language) lets you define tools declaratively - just describe what they do, and the system handles the rest.

## When to Use DSL vs Python

| Use DSL When...      | Use Python When...   |
| -------------------- | -------------------- |
| Simple calculations  | Complex logic needed |
| Data transformations | External API calls   |
| Quick utilities      | State management     |
| Prototyping ideas    | Event hooks required |
| Learning the system  | Production plugins   |

## Step 1: Create a DSL File

Create `my-utils.tools`:

```
## My Utilities - DSL Plugin Example
##
## This file demonstrates DSL-only plugin creation.
## No Python required - just define your tools declaratively!
##
## Usage:
##     pms plugin discover .
##     pms plugin call my-utils.double --arg x=21

# =============================================================================
# Math Tools
# =============================================================================

tool double:
    description: "Double a number"
    param x: int
    return x * 2

tool triple:
    description: "Triple a number"
    param x: int
    return x * 3

tool add:
    description: "Add two numbers"
    param a: int
    param b: int
    return a + b

tool percentage:
    description: "Calculate what percentage x is of total"
    param x: float
    param total: float
    return (x / total) * 100

tool is_even:
    description: "Check if a number is even"
    param n: int
    return n % 2 == 0

tool is_positive:
    description: "Check if a number is positive"
    param n: int
    return n > 0

# =============================================================================
# String Tools
# =============================================================================

tool greet:
    description: "Generate a greeting"
    param name: string = "World"
    return "Hello, " + name + "!"

tool shout:
    description: "Convert text to uppercase"
    param text: string
    return upper(text)

tool whisper:
    description: "Convert text to lowercase"
    param text: string
    return lower(text)

tool word_count:
    description: "Count words in text"
    param text: string
    return len(text.split())

# =============================================================================
# Conditional Tools
# =============================================================================

tool grade:
    description: "Convert score to letter grade"
    param score: int
    when score >= 90:
        return "A"
    when score >= 80:
        return "B"
    when score >= 70:
        return "C"
    when score >= 60:
        return "D"
    otherwise:
        return "F"

tool size_category:
    description: "Categorize a number by size"
    param n: int
    when n > 1000:
        return "huge"
    when n > 100:
        return "large"
    when n > 10:
        return "medium"
    when n > 0:
        return "small"
    otherwise:
        return "zero or negative"

tool temperature_feel:
    description: "Describe how a temperature feels"
    param celsius: float
    when celsius > 35:
        return "Hot! 🔥"
    when celsius > 25:
        return "Warm ☀️"
    when celsius > 15:
        return "Mild 🌤️"
    when celsius > 5:
        return "Cool 🌥️"
    otherwise:
        return "Cold! ❄️"

# =============================================================================
# List Tools
# =============================================================================

tool sum_list:
    description: "Sum all numbers in a list"
    param numbers: list
    return sum(numbers)

tool average:
    description: "Calculate average of numbers"
    param numbers: list
    return sum(numbers) / len(numbers)

tool max_value:
    description: "Find maximum value"
    param numbers: list
    return max(numbers)

tool min_value:
    description: "Find minimum value"
    param numbers: list
    return min(numbers)

tool list_length:
    description: "Count items in a list"
    param items: list
    return len(items)
```

## Step 2: Use Your DSL Plugin

```bash
# Discover the plugin
pms plugin discover .

# Call math tools
pms plugin call my-utils.double --arg x=21
# Output: 42

pms plugin call my-utils.percentage --arg x=25 --arg total=200
# Output: 12.5

pms plugin call my-utils.is_even --arg n=42
# Output: true

# Call string tools
pms plugin call my-utils.greet --arg name="Developer"
# Output: "Hello, Developer!"

pms plugin call my-utils.shout --arg text="hello world"
# Output: "HELLO WORLD"

# Call conditional tools
pms plugin call my-utils.grade --arg score=85
# Output: "B"

pms plugin call my-utils.temperature_feel --arg celsius=28
# Output: "Warm ☀️"

# Call list tools
pms plugin call my-utils.average --arg numbers='[10, 20, 30, 40]'
# Output: 25.0
```

## DSL Syntax Reference

### Basic Structure

```
tool <name>:
    description: "What this tool does"
    param <name>: <type> [= default]
    return <expression>
```

### Supported Types

- `int` - Integer numbers
- `float` - Decimal numbers
- `string` - Text
- `bool` - True/False
- `list` - Arrays

### Available Functions

| Function   | Description | Example                |
| ---------- | ----------- | ---------------------- |
| `len(x)`   | Length      | `len("hello")` → 5     |
| `sum(x)`   | Sum list    | `sum([1,2,3])` → 6     |
| `max(x)`   | Maximum     | `max([1,5,3])` → 5     |
| `min(x)`   | Minimum     | `min([1,5,3])` → 1     |
| `abs(x)`   | Absolute    | `abs(-5)` → 5          |
| `round(x)` | Round       | `round(3.7)` → 4       |
| `upper(x)` | Uppercase   | `upper("hi")` → "HI"   |
| `lower(x)` | Lowercase   | `lower("HI")` → "hi"   |
| `str(x)`   | To string   | `str(42)` → "42"       |
| `int(x)`   | To int      | `int("42")` → 42       |
| `float(x)` | To float    | `float("3.14")` → 3.14 |

### Operators

```
# Arithmetic
+  -  *  /  %  **

# Comparison
==  !=  <  >  <=  >=

# Boolean
and  or  not

# String
+  (concatenation)
```

### Conditionals

```
tool categorize:
    param x: int
    when x > 100:
        return "big"
    when x > 10:
        return "medium"
    otherwise:
        return "small"
```

## Combining DSL with Python Plugins

You can have both in the same directory:

```
my-plugin/
├── plugin.json      # Python plugin manifest
├── main.py          # Python implementation
└── helpers.tools    # DSL tools (auto-discovered)
```

The DSL tools will be available alongside your Python tools!

## Real-World DSL Examples

### Project Scoring

```
tool project_health:
    description: "Calculate project health score"
    param tasks_done: int
    param tasks_total: int
    param bugs_open: int
    return (tasks_done / tasks_total * 100) - (bugs_open * 5)
```

### Time Calculations

```
tool hours_to_days:
    description: "Convert hours to work days (8h/day)"
    param hours: float
    return hours / 8

tool estimate_completion:
    description: "Days until completion at current velocity"
    param remaining_tasks: int
    param tasks_per_day: float
    return remaining_tasks / tasks_per_day
```

### Status Helpers

```
tool task_priority:
    description: "Determine task priority based on factors"
    param days_old: int
    param is_blocking: bool
    param customer_reported: bool
    when customer_reported and days_old > 3:
        return "critical"
    when is_blocking:
        return "high"
    when days_old > 7:
        return "medium"
    otherwise:
        return "low"
```

## What You Learned

1. **DSL Syntax**: Declarative tool definitions
2. **No Python Needed**: Just describe, don't implement
3. **Built-in Functions**: len, sum, max, min, etc.
4. **Conditionals**: when/otherwise for branching logic
5. **Type System**: int, float, string, bool, list
6. **Quick Prototyping**: Test ideas without boilerplate

## When to Graduate to Python

Move to Python when you need:

- External API calls
- File system access
- Complex state management
- Event hooks
- Error handling beyond simple conditionals
- Custom data structures

## Next Steps

- **Tutorial 4**: Build an external API integration
- **Tutorial 5**: Create self-building meta-plugins
- **Tutorial 6**: Combine DSL + Python + Events

---

## Quick Reference Card

```
## DSL Quick Reference

# Basic tool
tool name:
    description: "What it does"
    param x: int
    return x * 2

# With default
tool greet:
    param name: string = "World"
    return "Hello, " + name

# Conditional
tool check:
    param n: int
    when n > 0:
        return "positive"
    otherwise:
        return "non-positive"

# Functions: len, sum, max, min, abs, round, upper, lower, str, int, float
# Operators: + - * / % ** == != < > <= >= and or not
# Types: int, float, string, bool, list
```
