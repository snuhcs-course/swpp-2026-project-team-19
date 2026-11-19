import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import { BottomSheet } from "./BottomSheet";
import { Button } from "./Button";
import { QueryView } from "./QueryView";
import { EmptyState, LOADING_FEEDBACK_DELAY_MS, LoadingState } from "./states";
import { TextField } from "./TextField";

describe("Button", () => {
  it("blocks a second press while busy", async () => {
    const onClick = vi.fn();
    render(
      <Button busy onClick={onClick}>
        저장
      </Button>,
    );

    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    expect(onClick).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "저장" })).toHaveAttribute("aria-busy", "true");
  });
});

describe("TextField", () => {
  it("links its label, and announces an error instead of the hint", () => {
    const { rerender } = render(<TextField label="매장 전화번호" hint="숫자만 입력해 주세요." />);
    const input = screen.getByLabelText("매장 전화번호");
    expect(input).toHaveAccessibleDescription("숫자만 입력해 주세요.");
    expect(input).not.toHaveAttribute("aria-invalid");

    rerender(<TextField label="매장 전화번호" hint="숫자만 입력해 주세요." error="너무 길어요." />);

    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("너무 길어요.");
    expect(screen.getByRole("alert")).toHaveTextContent("너무 길어요.");
  });
});

describe("BottomSheet", () => {
  function Example({ onClose = () => undefined }: { onClose?: () => void }) {
    const [open, setOpen] = useState(true);
    return (
      <BottomSheet
        open={open}
        title="메뉴를 삭제할까요?"
        onClose={() => {
          onClose();
          setOpen(false);
        }}
      >
        <Button onClick={() => setOpen(false)}>취소</Button>
      </BottomSheet>
    );
  }

  it("opens as a titled dialog and closes from its own button", async () => {
    render(<Example />);
    const dialog = screen.getByRole("dialog", { name: "메뉴를 삭제할까요?" });
    expect(dialog).toHaveAttribute("open");

    await userEvent.click(screen.getByRole("button", { name: "취소" }));

    expect(dialog).not.toHaveAttribute("open");
  });

  it("asks to close on Escape and on a click outside its content", async () => {
    const onClose = vi.fn();
    render(<Example onClose={onClose} />);
    const dialog = screen.getByRole("dialog");

    dialog.dispatchEvent(new Event("cancel", { cancelable: true }));
    expect(onClose).toHaveBeenCalledTimes(1);

    render(<Example onClose={onClose} />);
    await userEvent.click(screen.getAllByRole("dialog").at(-1)!);
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

describe("LoadingState", () => {
  it("shows the spinner only after a short delay, so quick loads do not flash", () => {
    vi.useFakeTimers();
    try {
      render(<LoadingState message="불러오는 중" />);
      expect(screen.getByRole("status")).toHaveTextContent("불러오는 중");
      expect(document.querySelector("[class*=spinner]")).toBeNull();

      act(() => vi.advanceTimersByTime(LOADING_FEEDBACK_DELAY_MS));

      expect(document.querySelector("[class*=spinner]")).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("QueryView", () => {
  const base = { data: undefined, error: null, isPending: false, isError: false, isFetching: false, refetch: vi.fn() };

  it("shows loading, then the data", () => {
    const { rerender } = render(
      <QueryView query={{ ...base, isPending: true }}>{(data: string[]) => <p>{data.join(",")}</p>}</QueryView>,
    );
    expect(screen.getByRole("status")).toBeInTheDocument();

    rerender(<QueryView query={{ ...base, data: ["a", "b"] }}>{(data: string[]) => <p>{data.join(",")}</p>}</QueryView>);

    expect(screen.getByText("a,b")).toBeInTheDocument();
  });

  it("shows the empty state for empty data", () => {
    render(
      <QueryView query={{ ...base, data: [] as string[] }} isEmpty={(data) => data.length === 0} empty={<EmptyState title="메뉴가 없어요" />}>
        {() => <p>목록</p>}
      </QueryView>,
    );

    expect(screen.getByText("메뉴가 없어요")).toBeInTheDocument();
    expect(screen.queryByText("목록")).not.toBeInTheDocument();
  });

  it("offers a retry for an error that a retry may fix", async () => {
    const refetch = vi.fn();
    render(
      <QueryView query={{ ...base, isError: true, error: new ApiError(0, null), refetch }}>{() => null}</QueryView>,
    );

    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));

    expect(refetch).toHaveBeenCalledOnce();
  });

  it("offers no retry for 403", () => {
    render(
      <QueryView query={{ ...base, isError: true, error: new ApiError(403, { code: "FORBIDDEN" }) }}>{() => null}</QueryView>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("이 화면을 볼 권한이 없어요.");
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
  });
});
