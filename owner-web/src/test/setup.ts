import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

// jsdom has no object URLs; photo previews only need a string.
if (!URL.createObjectURL) {
  let next = 0;
  URL.createObjectURL = () => `blob:test/${++next}`;
  URL.revokeObjectURL = () => undefined;
}

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  sessionStorage.clear();
  localStorage.clear();
  window.history.replaceState(null, "", "/");
});

afterAll(() => {
  server.close();
});
