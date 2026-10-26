---
id: design-domain-events
name: Domain events
description: "When core logic ends by calling several unrelated side-effect systems, publish a frozen event to a dispatcher built in the entry point and let handlers subscribed by event class react."
scope: scoped
globs:
  - "**/*.py"
section: common-patterns
priority: 69
tags: [python, design, patterns]
---

# Domain events

## Description

A function that performs one core action (register a user, upgrade a plan) and then calls mail, chat, metrics and logging inline buries its one line of business logic under notification plumbing. Every such function imports every side-effect system, and adding a channel means editing all of them. Separate the two: the core action publishes an event describing what happened, and handlers subscribed to that event class do the side effects. The publisher knows nothing about its handlers, and a new channel is one new handler.

## Bad Example

```python
def register_user(name: str, email: str) -> User:
    user = users.create(name, email)
    post_chat_message("sales", f"{user.name} registered with {user.email}.")
    send_email(user.email, "Welcome", f"Thanks for registering, {user.name}!")
    logger.info("user registered: %s", user.id)
    return user
```

## Good Example

```python
@dataclass(frozen=True)
class UserRegistered:
    user_id: UserId
    email: EmailAddress  # a value object, never a bare str
    occurred_at: datetime  # aware UTC, from the injected clock


E = TypeVar("E")


class EventDispatcher:  # built once in the entry point, passed to publishers
    def __init__(self) -> None:
        self._handlers: defaultdict[type, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        if handler not in self._handlers[event_type]:  # a second setup run must not double-notify
            self._handlers[event_type].append(handler)

    def publish(self, event: object) -> None:
        for handler in self._handlers.get(type(event), ()):
            handler(event)


def register_user(
    name: str, email: EmailAddress, *, users: UserStore, events: EventDispatcher, clock: Clock
) -> User:
    user = users.create(name, email)
    events.publish(UserRegistered(user.id, user.email, occurred_at=clock()))
    return user


# main.py: wire every handler once.
events = EventDispatcher()
events.subscribe(UserRegistered, notify_sales)
events.subscribe(UserRegistered, send_welcome_email)
```

## Notes

- Signals: a function does its core job and then calls two or more unrelated side-effect systems; several functions share the same side-effect calls; a new channel means editing every caller.
- Progression: return event objects from the core and let the caller act on them; then a dispatcher object built in the entry point that maps event classes to handler lists; then an external queue when handlers must outlive the process.
- Key subscriptions by event class, never by string: a misspelled string event type notifies nobody and raises no error.
- Name events in the past tense as frozen dataclasses, with an aware UTC `occurred_at` (`datetime.now(timezone.utc)` behind the injected clock).
- Register once in the entry point, or make `subscribe` ignore a handler it already has: running setup twice otherwise handles every event twice.
- Decide the failure policy explicitly: let handler errors propagate, or isolate each handler and log with `logger.exception`; never swallow them silently.
- Not when there is one side effect with one caller: call it directly. A single reaction the caller passes in is `design-callback`.
- Observer, mediator and a dispatcher compared, and handler modules wired to a dispatcher: see observer-mediator-pubsub.md.
