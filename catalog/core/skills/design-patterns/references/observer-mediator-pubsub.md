# Observer, mediator and a dispatcher

Three ways to let one part of a program react to what another did, for `design-domain-events` and `design-callback`: the observer, the mediator, and a publish/subscribe dispatcher keyed by event class. This file compares them and walks through wiring handler modules to a dispatcher. A single reaction that the caller passes in is a callback (`design-callback`), not any of these.

## Contents

- Observer
- Mediator
- A dispatcher keyed by event class
- Handler modules
- Publishers after the change
- Wiring in the entry point
- Gotchas
- Choosing between them

## Observer

A subject keeps a list of observers and notifies each one when something happens.

```python
class Observer(Protocol):
    def notify(self, reading: Reading) -> None: ...


class Thermostat:
    def __init__(self) -> None:
        self._observers: list[Observer] = []

    def attach(self, observer: Observer) -> None:
        self._observers.append(observer)

    def detach(self, observer: Observer) -> None:
        self._observers.remove(observer)

    def record(self, reading: Reading) -> None:
        self._store(reading)
        for observer in self._observers:
            observer.notify(reading)
```

Limits:

- It couples one subject to its list of observers, so every subsystem (registration, plan upgrades, password resets) needs its own subject, or everything ends up in one.
- It scales poorly: a subject per action becomes impractical as the program grows.
- The subject already has a job; managing observers lowers its cohesion.

## Mediator

Components tell a mediator that something happened, and the mediator decides what to do. It suits components that must coordinate, such as a form whose button depends on its fields.

```python
class Mediator(Protocol):
    def notify(self, sender: object, event: FormEvent) -> None: ...


class SubmitButton:
    def __init__(self, mediator: Mediator) -> None:
        self._mediator = mediator

    def click(self) -> None:
        self._mediator.notify(self, FormEvent.SUBMIT_CLICKED)


class LoginForm:  # the mediator
    def __init__(self, email_field: TextField, start_login: Callable[[str], None]) -> None:
        self.email_field = email_field
        self._start_login = start_login

    def notify(self, sender: object, event: FormEvent) -> None:
        if event is FormEvent.SUBMIT_CLICKED:
            self.email_field.enabled = False
            self._start_login(self.email_field.value)
```

Limits:

- All the logic lives in the mediator; as component types grow, it gains methods and branches and its cohesion drops, until it becomes a god object.
- Every mediator has its own `notify` logic, so there is no standard way to extend it.

## A dispatcher keyed by event class

Publish/subscribe combines the two: it is central like a mediator and standard like an observer. A publisher posts an event to a dispatcher and knows nothing of who reacts; handlers subscribe to event classes. Events are frozen dataclasses named in the past tense, and the dispatcher is an object the entry point builds and passes to publishers, not a module-level dictionary.

```python
@dataclass(frozen=True)
class UserRegistered:
    user_id: UserId
    email: EmailAddress
    occurred_at: datetime


@dataclass(frozen=True)
class PlanUpgraded:
    user_id: UserId
    plan: Plan
    occurred_at: datetime


E = TypeVar("E")


class EventDispatcher:
    def __init__(self) -> None:
        self._handlers: defaultdict[type, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def publish(self, event: object) -> None:
        for handler in self._handlers.get(type(event), ()):
            handler(event)
```

## Handler modules

Each notification channel gets its own module: handler functions, plus one function that subscribes them to a dispatcher it receives. Importing the module registers nothing; only the entry point's call does.

```python
# handlers/email.py
def send_welcome(event: UserRegistered, *, send: SendEmail) -> None:
    send(event.email, "Welcome", "Thanks for registering.")


def send_upgrade_thanks(event: PlanUpgraded, *, send: SendEmail, users: UserStore) -> None:
    send(users.get(event.user_id).email, "Thank you", f"You are now on {event.plan.value}.")


def register_email_handlers(events: EventDispatcher, send: SendEmail, users: UserStore) -> None:
    events.subscribe(UserRegistered, partial(send_welcome, send=send))
    events.subscribe(PlanUpgraded, partial(send_upgrade_thanks, send=send, users=users))
```

```python
# handlers/audit.py
logger = logging.getLogger(__name__)


def log_registration(event: UserRegistered) -> None:
    logger.info("user registered", extra={"user_id": str(event.user_id)})


def register_audit_handlers(events: EventDispatcher) -> None:
    events.subscribe(UserRegistered, log_registration)
```

## Publishers after the change

The business functions do their job and publish one event. They import no mail, chat or logging code.

```python
def register_user(
    name: str, email: EmailAddress, *, users: UserStore, events: EventDispatcher, clock: Clock
) -> User:
    user = users.create(name, email)
    events.publish(UserRegistered(user.id, user.email, occurred_at=clock()))
    return user


def upgrade_plan(
    user_id: UserId, plan: Plan, *, users: UserStore, events: EventDispatcher, clock: Clock
) -> None:
    users.set_plan(user_id, plan)
    events.publish(PlanUpgraded(user_id, plan, occurred_at=clock()))
```

## Wiring in the entry point

The entry point builds the dispatcher once, registers every channel, and passes the dispatcher to the code that publishes. Turning a channel off is one line here, or a setting read here.

```python
def main(settings: Settings) -> None:
    users = build_user_store(settings)
    events = EventDispatcher()
    register_audit_handlers(events)
    register_email_handlers(events, send=build_mailer(settings).send, users=users)
    if settings.chat_notifications:
        register_chat_handlers(events, post=build_chat_client(settings).post)
    serve(users=users, events=events)
```

## Gotchas

- String event types fail silently: a misspelled `"user_pasword_forgotten"` notifies nobody and raises nothing. Keying by event class makes a typo an import or name error, and the event carries typed fields instead of a loose payload.
- Duplicate registration: running setup twice handles every event twice. Register once in the entry point, or make `subscribe` ignore a handler it already has, as above. Note that `partial(...)` builds a new object on each call, so two registrations of the same partial are not recognized as duplicates.
- Failure policy: decide whether a failing handler stops the others. Either let the error propagate to the publisher, or isolate each handler and log it with `logger.exception`; never swallow it.
- Handlers run in the publisher's call and transaction. A handler that must run only after the change is committed, or that must outlive the process, belongs behind a queue; where effects run relative to a commit is python-architecture's arch-effects-after-commit.

## Choosing between them

| Aspect | Observer | Mediator | Dispatcher (publish/subscribe) |
| --- | --- | --- | --- |
| Coupling | the subject knows the observer interface | components know the mediator interface | the publisher knows only the event and the dispatcher |
| Where logic lives | each observer's `notify` | the mediator class | the handler functions |
| Registration | the subject keeps its observer list | the mediator holds its components | the dispatcher maps event classes to handlers |
| Growth | one subject per subsystem, or one bloated subject | the mediator grows into a god object | add a handler module without touching publishers |
| Best for | one subject with a few local observers | coordinating interacting components, such as a form | decoupling side effects from core actions across a program |

Use an observer when the relationship is small, local and self-contained. Use a mediator when components must coordinate their state, and accept that it absorbs that complexity. Use a dispatcher when a core action triggers side effects in unrelated systems, which is the case `design-domain-events` covers. When none of that applies (one side effect, one caller), call the function directly.
