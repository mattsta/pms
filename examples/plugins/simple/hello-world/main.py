"""Hello World Plugin - The simplest possible PMS plugin.

This example demonstrates:
- Basic plugin structure
- Simple tool definitions
- Parameter handling with defaults
- Returning values from tools

Usage:
    # Discover and start the plugin
    pms plugin discover examples/plugins/simple
    pms plugin start hello-world

    # Call the tools
    pms plugin call hello-world.say_hello
    pms plugin call hello-world.say_hello --arg name=Alice
    pms plugin call hello-world.get_greeting --arg style=excited
"""


async def say_hello(name: str = "World") -> str:
    """Say hello to someone.

    Args:
        name: The name to greet (default: "World")

    Returns:
        A greeting message
    """
    message = f"Hello, {name}!"
    print(message)  # Also print to console
    return message


async def get_greeting(style: str = "casual") -> str:
    """Get a greeting message in different styles.

    Args:
        style: The greeting style (formal, casual, excited)

    Returns:
        A styled greeting message
    """
    greetings = {
        "formal": "Good day. I hope this message finds you well.",
        "casual": "Hey there! What's up?",
        "excited": "OMG HI!!! SO HAPPY TO SEE YOU!!!",
    }
    return greetings.get(style, greetings["casual"])


# Lifecycle hooks (optional)
async def on_load(config: dict = None):
    """Called when plugin is loaded."""
    print("Hello World plugin loaded!")


async def on_unload():
    """Called when plugin is unloaded."""
    print("Hello World plugin unloaded. Goodbye!")
