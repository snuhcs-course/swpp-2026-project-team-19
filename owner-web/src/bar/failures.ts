import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { ApiError, errorMessage } from "../api/errors";
import { ownerQueryKeys } from "../owner/queries";

/**
 * The failures every change to a bar shares (spec 3.7, 3.15.6, 3.16.6): 403 shows no retry and reads the bar
 * list again, so an owner who lost the bar is shut out by the access check; 404 BAR_NOT_FOUND goes to the bar
 * list. Returns the message to show, or null when the screen is left. `release` lets that move skip the
 * leave prompt.
 */
export function useBarFailure(release?: () => void) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  return (failure: unknown): string | null => {
    if (failure instanceof ApiError && failure.code === "FORBIDDEN") {
      void queryClient.invalidateQueries({ queryKey: ownerQueryKeys.myBars });
      return "이 매장을 관리할 권한이 없어요.";
    }
    if (failure instanceof ApiError && failure.code === "BAR_NOT_FOUND") {
      release?.();
      void queryClient.invalidateQueries({ queryKey: ownerQueryKeys.myBars });
      void navigate("/bars", { replace: true });
      return null;
    }
    return errorMessage(failure);
  };
}
