import { setupServer } from "msw/node";

/** The API in tests: each test adds the handlers it needs (server.use); an unhandled request fails the test. */
export const server = setupServer();
