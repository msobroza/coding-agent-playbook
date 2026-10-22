---
id: web-application
name: web-application
description: "Practices for Python web backends, shown with FastAPI and SQLAlchemy."
playbook:
  use_when: "writing or reviewing endpoints, schemas, auth or database code in a web app"
  files: "Web endpoints, database access and migrations"
  sections:
    - id: security
      title: "Security"
      impact: CRITICAL
      summary: "Authenticate callers safely and authorize every access to their data."
      open_when: "Code handles login, passwords, reset tokens, JWTs or CORS, or loads a record by an id the client sent."
    - id: database
      title: "Database"
      impact: CRITICAL
      summary: "Query, scope and evolve the database safely with SQLAlchemy and Alembic."
      open_when: "Code adds or changes an ORM model, a query, the per-request session or its commit, a relationship or an Alembic migration."
    - id: async-io
      title: "Async I/O"
      impact: CRITICAL
      summary: "Keep the event loop free and share outbound clients so one request cannot stall the others."
      open_when: "An async def route or dependency calls code that may block, or the app calls another HTTP service."
    - id: api-design
      title: "API design"
      impact: HIGH
      summary: "Shape what enters and leaves the API and map every failure to a precise status code."
      open_when: "A route's request or response model, HTTP method, success or error status code, or list paging changes."
    - id: app-structure
      title: "App structure"
      impact: HIGH
      summary: "Compose the app in a factory with explicit providers so resources and logic stay replaceable."
      open_when: "Code creates the app or a lifespan resource, adds a router or dependency provider, or grows logic in a route body."
    - id: observability
      title: "Observability"
      impact: MEDIUM
      summary: "Make each request traceable through the logs without leaking secrets."
      open_when: "Code adds logging, middleware or error reporting that should tie a log line to the request behind it."
    - id: testing
      title: "Testing"
      impact: MEDIUM
      summary: "Test through the real app and a real database, isolated per test."
      open_when: "A test calls an endpoint, overrides a dependency, or needs a database session or rows seeded for it."
    - id: api-conventions
      title: "API conventions"
      impact: MEDIUM
      summary: "Keep URLs, query parameters and generated docs predictable for clients."
      open_when: "A route's URL path, version prefix, query parameters, tags, summary or documented responses are added or renamed."
---

# Web application

Practices for Python web backends, shown with FastAPI and SQLAlchemy: authenticating callers and authorizing every access to their data, querying and migrating the database safely, keeping the event loop free, shaping request and response schemas and the status codes failures map to, composing the app from a factory and explicit dependency providers, tracing each request through the logs, testing through the real app and database, and keeping URLs, query parameters and generated docs predictable. Library-agnostic Python and Pydantic validation stay in the python-coding skill, and test code in general in the python-testing skill.
