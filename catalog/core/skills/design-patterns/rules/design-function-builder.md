---
id: design-function-builder
name: Function builder
description: "When configuration and runtime arguments arrive together, write a function that takes the configuration once and returns a configured function, so business code receives only the runtime arguments."
scope: scoped
globs:
  - "**/*.py"
section: specialized-patterns
priority: 82
tags: [python, design, patterns]
---

# Function builder

## Description

A function builder is a higher-order function: it takes configuration arguments and returns a new function that captures them in a closure. It separates configuration-time arguments (a server, a rate, a threshold) from runtime arguments (this customer, this order). The entry point calls the builder once; business code receives a function that matches the signature it expects and never sees the configuration. In its smallest form, `make_multiplier(3)` returns a function that multiplies by three.

## Bad Example

```python
def send_welcome_message(
    customer: Customer, smtp_host: str, smtp_port: int, username: str, password: str
) -> None:
    # Business code carries mail-server settings it never uses itself.
    server = SmtpServer(smtp_host, smtp_port, username, password)
    send_email(server, customer.email, "Welcome!", f"Hello {customer.name}!")
```

## Good Example

```python
class MessageSender(Protocol):
    def __call__(self, customer: Customer, *, subject: str, body: str) -> None: ...


def create_email_sender(config: MailSettings, send: SendEmail) -> MessageSender:
    """Capture the mail settings once; return a sender that needs only the message."""

    def send_to_customer(customer: Customer, *, subject: str, body: str) -> None:
        send(config, to_address=customer.email, subject=subject, body=body)

    return send_to_customer


def send_welcome_message(customer: Customer, sender: MessageSender) -> None:
    sender(customer, subject="Welcome!", body=f"Hello {customer.name}, welcome aboard!")


def main() -> None:
    settings = load_settings()  # host, port and credentials from the environment
    sender = create_email_sender(settings.mail, send=smtp_send)
    send_welcome_message(Customer(name="Ada", email="ada@example.com"), sender)
```

A test passes a recording function as `sender` and checks the subject and body, with no mail server.

## Notes

- Compared with a wrapper plus `functools.partial` at each call site, the builder hides how the function is configured: callers get a function that already fits the seam.
- When the configuration should be inspectable (logged, compared, shown in a repr), promote the closure to a callable frozen dataclass whose fields hold the settings and whose `__call__` does the work.
- Partial versus closure mechanics, and the late-binding trap, are python-closures-and-partial in the python-coding skill.
- A builder that returns one configured strategy is design-strategy's closure step; a function that only translates arguments and returns the result at once is design-function-wrapper.
- Stop when the configuration is used once: pass it directly.
