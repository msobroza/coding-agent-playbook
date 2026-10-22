---
id: arch-effects-after-commit
name: Effects after commit
description: "Effects that leave the process (emails, broker messages, webhooks) run after the commit, or go into an outbox row written in the same transaction; never send first and commit second."
version: 1
scope: scoped
globs:
  - "**/services/**/*.py"
  - "**/use_cases/**/*.py"
  - "**/usecases/**/*.py"
  - "**/application/**/*.py"
  - "**/operations/**/*.py"
  - "**/worker.py"
  - "**/workers/**/*.py"
  - "**/outbox.py"
section: persistence
priority: 50
tags: [python, architecture, transactions]
---

# Send outside effects only after the commit

## Description

A database transaction can be rolled back; an email cannot be unsent. When a use case sends a message and then commits, a failed commit leaves the outside world believing in a change the database never saved: a confirmation for a booking that does not exist, an event for an order that was rolled back.

Run each effect that leaves the process after the commit succeeds. When the effect must not be lost either (a crash between commit and send drops it), write it as an outbox row in the same transaction as the change, and let a worker deliver it afterwards.

## Bad Example

```python
def book_and_confirm(
    uow: HotelUnitOfWork, send_email: SendEmail, request: BookingRequest
) -> Booking:
    booking = Booking.create(uow.rooms.get(request.room_id), request)
    uow.bookings.add(booking)
    send_email(request.email, confirmation_text(booking))  # sent before anything is saved
    uow.commit()  # a constraint violation here leaves a confirmation for no booking
    return booking
```

## Good Example

```python
def book_and_confirm(
    uow: HotelUnitOfWork, send_email: SendEmail, request: BookingRequest
) -> Booking:
    booking = Booking.create(uow.rooms.get(request.room_id), request)
    uow.bookings.add(booking)
    uow.commit()
    send_email(request.email, confirmation_text(booking))  # only a saved booking is confirmed
    return booking


def book_and_queue_confirmation(uow: HotelUnitOfWork, request: BookingRequest) -> Booking:
    booking = Booking.create(uow.rooms.get(request.room_id), request)
    uow.bookings.add(booking)
    uow.outbox.add(OutboxMessage.confirmation(booking, request.email))  # same transaction
    uow.commit()  # the booking and its pending email are saved together
    return booking
```

A worker reads unsent outbox rows, delivers each one and marks it sent.

## Notes

- Choose by cost of loss: sending after the commit can drop an effect when the process dies in between; the outbox delivers it at least once.
- At-least-once delivery means a message can arrive twice: outbox consumers and the systems they call must be idempotent (a message id the receiver checks, or an upsert).
- Remote sends keep their timeout and bounded retry (the python-coding skill's python-retries-and-timeouts rule), and a failed send after a successful commit is reported, never turned into a rollback of saved work.
- Asynchronous projections fed from an outbox or event log show their freshness to readers.
- The commit itself belongs to the use case (arch-unit-of-work); in a web app the web-application skill's sqlalchemy-transaction-boundary rule names this rule for the outbox form.
