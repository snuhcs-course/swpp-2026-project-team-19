import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { bar, errorBody, useOwnerApi } from "../test/api";
import { renderOwnerWeb } from "../test/render";
import { server } from "../test/server";
import type { BarPhoto } from "../owner/queries";

vi.mock("../images/prepare", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../images/prepare")>()),
  // jsdom has no canvas: a "prepared" photo carries its file name, so uploads can be told apart.
  prepareImage: vi.fn(async (file: File) => ({
    blob: new Blob([`img-${file.name}`], { type: "image/jpeg" }),
    fileName: file.name.replace(/\.[^.]*$/, "") + ".jpg",
    width: 100,
    height: 100,
  })),
}));

const BAR_ID = "22222222-2222-4222-8222-222222222222";
const user = () => userEvent.setup();
const title = (name: string) => screen.findByRole("heading", { level: 1, name });
const file = (name: string) => new File([name], name, { type: "image/jpeg" });
const photo = (id: string): BarPhoto => ({
  photoId: id,
  imageUrl: `http://localhost/api/bar-photos/${id}`,
  thumbnailUrl: `http://localhost/api/bar-photos/${id}/thumbnail`,
});

type Answer = (request: { kind: string; name?: string; ids?: string[] }) => Response | undefined | Promise<Response | undefined>;

/** The bar's photos on a server that keeps POST, DELETE and PUT order (spec 3.16.2 to 3.16.4). */
function photoServer(initial: string[], answer?: Answer) {
  let photos = initial.map(photo);
  let next = 0;
  const calls: string[] = [];
  useOwnerApi();
  const current = () => bar(BAR_ID, "관악 위스키 바", { photos });
  server.use(
    http.get("/api/me/bars", () => HttpResponse.json({ items: [current()] })),
    http.get("/api/bars/:barId", () => HttpResponse.json(current())),
    http.post("/api/bars/:barId/photos", async ({ request }) => {
      // The mocked prepareImage writes "img-<file name>" into each photo.
      const image = (await request.formData()).get("image") as Blob;
      const name = (await image.text()).replace(/^img-/, "");
      calls.push(`POST ${name}`);
      const custom = await answer?.({ kind: "POST", name });
      if (custom) return custom;
      photos = [...photos, photo(`new-${++next}-${name}`)];
      return HttpResponse.json({ photos }, { status: 201 });
    }),
    http.delete("/api/bars/:barId/photos/:photoId", async ({ params }) => {
      calls.push(`DELETE ${String(params.photoId)}`);
      const custom = await answer?.({ kind: "DELETE" });
      if (custom) return custom;
      photos = photos.filter((item) => item.photoId !== params.photoId);
      return HttpResponse.json({ photos });
    }),
    http.put("/api/bars/:barId/photos/order", async ({ request }) => {
      const { photoIds } = (await request.json()) as { photoIds: string[] };
      calls.push(`PUT ${photoIds.join(",")}`);
      const custom = await answer?.({ kind: "PUT", ids: photoIds });
      if (custom) return custom;
      photos = photoIds.map((id) => photos.find((item) => item.photoId === id)!);
      return HttpResponse.json({ photos });
    }),
  );
  return {
    calls,
    photos: () => photos.map((item) => item.photoId),
    /** Changes the photos as another device would. */
    setPhotos: (ids: string[]) => {
      photos = ids.map(photo);
    },
  };
}

async function openPhotos() {
  const view = renderOwnerWeb(`/bars/${BAR_ID}/photos`);
  await title("매장 사진 편집");
  await screen.findByRole("list", { name: "매장 사진" });
  return view;
}

const tiles = () => within(screen.getByRole("list", { name: "매장 사진" })).getAllByRole("listitem");
const tileNames = () => tiles().map((tile) => tile.getAttribute("aria-label"));
const upload = (...names: string[]) => user().upload(screen.getByLabelText("+ 사진 추가"), names.map(file));

describe("bar photos (OwnerPhotoHtmlV4Screen.kt, spec 3.16)", () => {
  it("shows the thumbnails with the cover first", async () => {
    photoServer(["p1", "p2"]);
    await openPhotos();

    expect(tileNames()).toEqual(["대표 사진", "사진 2"]);
    expect(tiles()[0]!.querySelector("img")).toHaveAttribute("src", "http://localhost/api/bar-photos/p1/thumbnail");
    expect(tiles()[1]!.querySelector("img")).toHaveAttribute("src", "http://localhost/api/bar-photos/p2/thumbnail");
    expect(within(tiles()[0]!).getByText("대표")).toBeInTheDocument();
  });

  it("uploads one photo at a time, and a failed one does not stop the others", async () => {
    const api = photoServer(["p1"], ({ kind, name }) =>
      kind === "POST" && name === "b.jpg" && !api.calls.includes("retry") ? HttpResponse.json(errorBody("INTERNAL_ERROR"), { status: 500 }) : undefined,
    );
    await openPhotos();

    await upload("a.jpg", "b.jpg", "c.jpg");

    await waitFor(() => expect(api.calls).toEqual(["POST a.jpg", "POST b.jpg", "POST c.jpg"]));
    await waitFor(() => expect(api.photos()).toHaveLength(3));
    const failed = await screen.findByRole("listitem", { name: "올리는 사진 b.jpg" });
    expect(within(failed).getByText("서버에서 문제가 생겼어요. 잠시 후 다시 시도해 주세요.")).toBeInTheDocument();

    api.calls.push("retry");
    await user().click(within(failed).getByRole("button", { name: "다시 시도" }));

    await waitFor(() => expect(api.photos()).toHaveLength(4));
    expect(screen.queryByRole("listitem", { name: "올리는 사진 b.jpg" })).not.toBeInTheDocument();
    expect(tileNames()).toHaveLength(4);
  });

  it.each([
    ["too large (413)", HttpResponse.json(errorBody("UPLOAD_TOO_LARGE"), { status: 413 }), "사진이 너무 커요. 다른 사진을 골라 주세요."],
    ["not an image the server reads (415)", HttpResponse.json(errorBody("UNSUPPORTED_IMAGE_TYPE"), { status: 415 }), "이 사진은 올릴 수 없어요. 다른 사진을 골라 주세요."],
  ])("marks only the photo that is %s", async (_, response, message) => {
    photoServer(["p1"], ({ kind, name }) => (kind === "POST" && name === "bad.jpg" ? response.clone() : undefined));
    await openPhotos();

    await upload("bad.jpg", "good.jpg");

    const failed = await screen.findByRole("listitem", { name: "올리는 사진 bad.jpg" });
    expect(await within(failed).findByText(message)).toBeInTheDocument();
    await waitFor(() => expect(tileNames()).toEqual(["대표 사진", "사진 2", "올리는 사진 bad.jpg"]));
    // Removing the failed photo from the list.
    await user().click(within(failed).getByRole("button", { name: "빼기" }));
    expect(screen.queryByRole("listitem", { name: "올리는 사진 bad.jpg" })).not.toBeInTheDocument();
  });

  it("drops a photo already on the bar (PHOTO_EXISTS) and reads the bar again", async () => {
    photoServer(["p1"], ({ kind }) => (kind === "POST" ? HttpResponse.json(errorBody("PHOTO_EXISTS"), { status: 409 }) : undefined));
    await openPhotos();

    await upload("same.jpg");

    expect(await screen.findByText("이미 등록된 사진이에요.")).toBeInTheDocument();
    expect(screen.queryByRole("listitem", { name: "올리는 사진 same.jpg" })).not.toBeInTheDocument();
  });

  it("stops the waiting photos when the bar is full (PHOTO_LIMIT_REACHED)", async () => {
    const api = photoServer(["p1"], ({ kind }) => (kind === "POST" ? HttpResponse.json(errorBody("PHOTO_LIMIT_REACHED"), { status: 409 }) : undefined));
    await openPhotos();

    await upload("a.jpg", "b.jpg");

    await waitFor(() => expect(screen.getAllByText("사진이 이미 15장이에요. 사진을 지운 뒤 다시 추가해 주세요.")).toHaveLength(2));
    expect(api.calls).toEqual(["POST a.jpg"]);
  });

  it("lets a photo stopped by the limit try again once a photo is deleted", async () => {
    // Codex review on #198: the failed photo already holds its place, so it is not counted against itself.
    // Another device fills the bar just before this upload arrives.
    const fourteen = Array.from({ length: 14 }, (_, index) => `p${index}`);
    let full = true;
    const api = photoServer(fourteen, ({ kind }) => {
      if (kind !== "POST" || !full) return undefined;
      api.setPhotos([...fourteen, "other"]);
      return HttpResponse.json(errorBody("PHOTO_LIMIT_REACHED"), { status: 409 });
    });
    await openPhotos();
    await upload("a.jpg");
    await screen.findByText("사진이 이미 15장이에요. 사진을 지운 뒤 다시 추가해 주세요.");
    await waitFor(() => expect(tiles()).toHaveLength(16));
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeDisabled();

    await user().click(screen.getByRole("button", { name: "사진 15 메뉴" }));
    await user().click(screen.getByRole("button", { name: "삭제하기" }));
    await user().click(within(screen.getByRole("dialog", { name: "사진을 삭제할까요?" })).getByRole("button", { name: "삭제하기" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "다시 시도" })).toBeEnabled());
    full = false;
    await user().click(screen.getByRole("button", { name: "다시 시도" }));

    await waitFor(() => expect(api.photos()).toHaveLength(15));
    expect(api.calls).toEqual(["POST a.jpg", "DELETE other", "POST a.jpg"]);
  });

  it("takes only as many photos as the bar has room for", async () => {
    const api = photoServer(Array.from({ length: 14 }, (_, index) => `p${index}`));
    await openPhotos();

    await upload("a.jpg", "b.jpg");

    expect(screen.getByText("매장 사진은 최대 15장까지 등록할 수 있어요.")).toBeInTheDocument();
    await waitFor(() => expect(api.calls).toEqual(["POST a.jpg"]));
    await waitFor(() => expect(screen.getByLabelText("+ 사진 추가")).toBeDisabled());
  });

  it("deletes after asking", async () => {
    const api = photoServer(["p1", "p2"]);
    await openPhotos();

    await user().click(screen.getByRole("button", { name: "사진 2 메뉴" }));
    await user().click(screen.getByRole("button", { name: "삭제하기" }));
    const sheet = screen.getByRole("dialog", { name: "사진을 삭제할까요?" });
    expect(within(sheet).getByText("삭제한 사진은 고객 화면에서도 바로 사라집니다.")).toBeInTheDocument();
    await user().click(within(sheet).getByRole("button", { name: "취소" }));
    expect(api.calls).toEqual([]);

    await user().click(screen.getByRole("button", { name: "사진 2 메뉴" }));
    await user().click(screen.getByRole("button", { name: "삭제하기" }));
    await user().click(within(screen.getByRole("dialog", { name: "사진을 삭제할까요?" })).getByRole("button", { name: "삭제하기" }));

    await waitFor(() => expect(tileNames()).toEqual(["대표 사진"]));
    expect(api.calls).toEqual(["DELETE p2"]);
  });

  it("keeps the last photo, as the app does", async () => {
    const api = photoServer(["p1"]);
    await openPhotos();

    await user().click(screen.getByRole("button", { name: "대표 사진 메뉴" }));
    await user().click(screen.getByRole("button", { name: "삭제하기" }));

    expect(screen.getByText("마지막 사진은 삭제할 수 없어요.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.calls).toEqual([]);
  });

  it("reads the bar again when the photo was already deleted (PHOTO_NOT_FOUND)", async () => {
    photoServer(["p1", "p2"], ({ kind }) => (kind === "DELETE" ? HttpResponse.json(errorBody("PHOTO_NOT_FOUND"), { status: 404 }) : undefined));
    await openPhotos();

    await user().click(screen.getByRole("button", { name: "사진 2 메뉴" }));
    await user().click(screen.getByRole("button", { name: "삭제하기" }));
    await user().click(within(screen.getByRole("dialog")).getByRole("button", { name: "삭제하기" }));

    expect(await screen.findByText("이미 삭제된 사진이에요.")).toBeInTheDocument();
  });

  it("sets the cover and moves the other photos, never the cover with the arrows", async () => {
    const api = photoServer(["p1", "p2", "p3"]);
    await openPhotos();

    expect(screen.getByRole("button", { name: "사진 1 앞으로" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "사진 1 뒤로" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "사진 2 앞으로" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "사진 3 뒤로" })).toBeDisabled();

    await user().click(screen.getByRole("button", { name: "사진 2 뒤로" }));
    await waitFor(() => expect(api.photos()).toEqual(["p1", "p3", "p2"]));

    await user().click(screen.getByRole("button", { name: "사진 3 메뉴" }));
    await user().click(screen.getByRole("button", { name: "대표 사진 등록" }));
    await waitFor(() => expect(api.photos()).toEqual(["p2", "p1", "p3"]));
    expect(api.calls).toEqual(["PUT p1,p3,p2", "PUT p2,p1,p3"]);
  });

  it("shows the current photos when they changed elsewhere (PHOTOS_OUTDATED)", async () => {
    const api = photoServer(["p1", "p2"], ({ kind }) => {
      if (kind !== "PUT") return undefined;
      // Another device added a photo meanwhile.
      api.setPhotos(["p1", "p2", "p9"]);
      return HttpResponse.json(
        { error: { code: "PHOTOS_OUTDATED", message: "바뀜", details: { photos: [photo("p1"), photo("p2"), photo("p9")] }, fieldErrors: [] } },
        { status: 409 },
      );
    });
    await openPhotos();

    await user().click(screen.getByRole("button", { name: "사진 2 메뉴" }));
    await user().click(screen.getByRole("button", { name: "대표 사진 등록" }));

    expect(await screen.findByText("다른 곳에서 사진이 바뀌었어요. 다시 정렬해 주세요.")).toBeInTheDocument();
    await waitFor(() => expect(tileNames()).toHaveLength(3));
  });

  it("refuses to leave while uploading, and asks while a failed photo is left", async () => {
    let answer: (() => void) | null = null;
    const api = photoServer(["p1"], async ({ kind }) => {
      if (kind !== "POST") return undefined;
      await new Promise<void>((resolve) => (answer = resolve));
      return HttpResponse.json(errorBody("INTERNAL_ERROR"), { status: 500 });
    });
    const { router } = await openPhotos();

    await upload("a.jpg");
    await waitFor(() => expect(answer).not.toBeNull());
    await user().click(screen.getByRole("button", { name: "뒤로" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}/photos`);

    answer!();
    await screen.findByRole("button", { name: "다시 시도" });
    await user().click(screen.getByRole("button", { name: "뒤로" }));

    expect(await screen.findByRole("dialog", { name: "변경을 취소할까요?" })).toBeInTheDocument();
    expect(api.calls).toEqual(["POST a.jpg"]);
  });
});

describe("photos of two bars", () => {
  it("starts afresh on another bar's photos, so a failed photo of one bar is never sent to the other", async () => {
    // Codex review on #198: the same screen of another bar, reached straight through the browser's history.
    const OTHER_ID = "33333333-3333-4333-8333-333333333333";
    const posts: string[] = [];
    useOwnerApi({ bars: [bar(BAR_ID, "관악 위스키 바", { photos: [photo("p1")] }), bar(OTHER_ID, "신림 바", { photos: [photo("q1")] })] });
    server.use(
      http.post("/api/bars/:barId/photos", ({ params }) => {
        posts.push(String(params.barId));
        return HttpResponse.json(errorBody("INTERNAL_ERROR"), { status: 500 });
      }),
    );
    // The other bar was opened before, so it is cached and shows at once.
    const { router } = await openPhotos();
    await router.navigate(`/bars/${OTHER_ID}/photos`);
    await waitFor(() => expect(screen.getByRole("list", { name: "매장 사진" }).querySelector("img")?.getAttribute("src")).toContain("/q1/"));
    await router.navigate(`/bars/${BAR_ID}/photos`);
    await waitFor(() => expect(screen.getByRole("list", { name: "매장 사진" }).querySelector("img")?.getAttribute("src")).toContain("/p1/"));
    await upload("a.jpg");
    await screen.findByRole("button", { name: "다시 시도" });

    void router.navigate(`/bars/${OTHER_ID}/photos`);
    await user().click(within(await screen.findByRole("dialog", { name: "변경을 취소할까요?" })).getByRole("button", { name: "변경 취소" }));

    await waitFor(() => expect(router.state.location.pathname).toBe(`/owner/bars/${OTHER_ID}/photos`));
    await waitFor(() => expect(screen.getByRole("list", { name: "매장 사진" }).querySelector("img")?.getAttribute("src")).toContain("/q1/"));
    expect(tileNames()).toEqual(["대표 사진"]);
    expect(screen.queryByRole("listitem", { name: "올리는 사진 a.jpg" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
    expect(posts).toEqual([BAR_ID]);
  });
});

describe("photos on the info form", () => {
  it("shows the thumbnails and opens the editor, asking first when the form has edits", async () => {
    photoServer(["p1", "p2"]);
    server.use(http.patch("/api/bars/:barId", () => HttpResponse.json(bar(BAR_ID, "관악 위스키 바"))));
    const { router } = renderOwnerWeb(`/bars/${BAR_ID}/info`);
    await screen.findByRole("button", { name: "저장하기" });

    const strip = screen.getByRole("list", { name: "매장 사진 목록" });
    expect(within(strip).getByRole("img", { name: "대표 사진" })).toHaveAttribute("src", "http://localhost/api/bar-photos/p1/thumbnail");

    await user().type(screen.getByLabelText("한 줄 소개"), "!");
    await user().click(screen.getByRole("link", { name: "편집 ›" }));

    expect(await screen.findByRole("dialog", { name: "변경을 취소할까요?" })).toBeInTheDocument();
    await user().click(screen.getByRole("button", { name: "변경 취소" }));
    await title("매장 사진 편집");
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}/photos`);
  });
});
