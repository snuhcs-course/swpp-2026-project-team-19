/** When a daily limit resets (spec 3.11.14 details.retryAfter, RFC 3339), in Seoul time: "11월 21일 0시". */
export function formatResetTime(retryAfter: unknown): string | null {
  if (typeof retryAfter !== "string") return null;
  const date = new Date(retryAfter);
  if (Number.isNaN(date.getTime())) return null;
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", hourCycle: "h23" })
      .formatToParts(date)
      .map((part) => [part.type, part.value]),
  );
  const minute = parts.minute && parts.minute !== "00" ? ` ${Number(parts.minute)}분` : "";
  return `${parts.month}월 ${parts.day}일 ${Number(parts.hour)}시${minute}`;
}
