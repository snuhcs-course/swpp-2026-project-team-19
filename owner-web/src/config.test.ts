import { afterEach, describe, expect, it } from "vitest";
import { readConfig } from "./config";

describe("readConfig", () => {
  afterEach(() => {
    delete window.BOTTLEMAP_OWNER_CONFIG;
  });

  it("reads the settings config.js put on the window", () => {
    window.BOTTLEMAP_OWNER_CONFIG = {
      supabaseUrl: "https://project-ref.supabase.co",
      supabasePublishableKey: "sb_publishable_example",
      kakaoJavascriptKey: null,
    };

    expect(readConfig()).toEqual({
      supabaseUrl: "https://project-ref.supabase.co",
      supabasePublishableKey: "sb_publishable_example",
      kakaoJavascriptKey: null,
    });
  });

  it("gives null for every setting when config.js did not load", () => {
    expect(readConfig()).toEqual({ supabaseUrl: null, supabasePublishableKey: null, kakaoJavascriptKey: null });
  });

  it("ignores values that are not non-empty strings", () => {
    expect(readConfig({ supabaseUrl: 42, supabasePublishableKey: " ", kakaoJavascriptKey: "kakao-js-key" })).toEqual({
      supabaseUrl: null,
      supabasePublishableKey: null,
      kakaoJavascriptKey: "kakao-js-key",
    });
    expect(readConfig("not an object")).toEqual({
      supabaseUrl: null,
      supabasePublishableKey: null,
      kakaoJavascriptKey: null,
    });
  });
});
