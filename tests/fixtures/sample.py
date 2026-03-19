import os


def greet(name: str) -> str:
    return f"Hello, {name}!"


class Calculator:
    def __init__(self):
        self.history = []

    def add(self, a: int, b: int) -> int:
        result = a + b
        self.history.append(result)
        return result
