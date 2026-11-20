import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import type { PreparedImage } from "../images/prepare";
import { useMe } from "../owner/queries";
import { clearDraft, emptyDraft, loadDraft, saveDraft, type ApplicationDraft } from "./draft";
import { pickedPhoto } from "./photos";
import type { StepId } from "./steps";

/** A photo picked on this visit, with a preview URL for its thumbnail. */
export interface PickedPhoto {
  id: string;
  image: PreparedImage;
  previewUrl: string;
}

interface Application {
  draft: ApplicationDraft;
  /** Always the latest draft, for async work that must compare against what is on screen now. */
  latest: () => ApplicationDraft;
  update: (change: Partial<ApplicationDraft> | ((draft: ApplicationDraft) => ApplicationDraft)) => void;
  cover: PickedPhoto | null;
  setCover: (image: PreparedImage | null) => void;
  menus: PickedPhoto[];
  setMenus: (change: (menus: PickedPhoto[]) => PickedPhoto[]) => void;
  /** A message to show on a step the owner is sent back to (e.g. by a refused submission). */
  notices: Partial<Record<StepId, string>>;
  setNotice: (step: StepId, message: string | null) => void;
  /** Whether the current step was opened from review ("수정"), so finishing it returns there. */
  editingReview: boolean;
  go: (step: StepId, options?: { replace?: boolean; fromReview?: boolean }) => void;
  /** The next step, or back to review when editing from it (forward() in OwnerOnboardingScreen.kt). */
  forward: (step: StepId) => void;
  /** Ends the application on this browser: drops the draft and the photos. */
  finish: () => void;
  /** Whether the owner is on `step` now (for async work that finishes after they may have moved on). */
  isAt: (step: StepId) => boolean;
  /** Whether a business certificate is being read, so the reading screen has something to wait for. */
  reading: boolean;
  setReading: (reading: boolean) => void;
}

const ApplicationContext = createContext<Application | null>(null);

/** The application in progress: the saved draft, the photos of this visit, and moving between steps. */
export function ApplicationProvider({ children }: { children: ReactNode }) {
  const userId = useMe().data?.userId ?? "";
  const navigate = useNavigate();
  const location = useLocation();
  const [draft, setDraft] = useState<ApplicationDraft>(() => loadDraft(userId) ?? emptyDraft());
  const latestDraft = useRef(draft);
  const [cover, setCoverState] = useState<PickedPhoto | null>(null);
  const [menus, setMenusState] = useState<PickedPhoto[]>([]);
  const [notices, setNotices] = useState<Partial<Record<StepId, string>>>({});
  const [reading, setReading] = useState(false);
  const finished = useRef(false);
  const path = useRef(location.pathname);
  useEffect(() => {
    path.current = location.pathname;
  }, [location.pathname]);

  const update = useCallback(
    (change: Partial<ApplicationDraft> | ((current: ApplicationDraft) => ApplicationDraft)) => {
      const next = typeof change === "function" ? change(latestDraft.current) : { ...latestDraft.current, ...change };
      latestDraft.current = next;
      setDraft(next);
      if (!finished.current && userId) saveDraft(userId, next);
    },
    [userId],
  );

  const setCover = useCallback((image: PreparedImage | null) => {
    setCoverState((previous) => {
      if (previous) URL.revokeObjectURL(previous.previewUrl);
      return image ? pickedPhoto(image) : null;
    });
  }, []);

  const setMenus = useCallback((change: (current: PickedPhoto[]) => PickedPhoto[]) => {
    setMenusState((previous) => {
      const next = change(previous);
      for (const photo of previous) if (!next.includes(photo)) URL.revokeObjectURL(photo.previewUrl);
      return next;
    });
  }, []);

  const setNotice = useCallback((step: StepId, message: string | null) => {
    setNotices((current) => ({ ...current, [step]: message ?? undefined }));
  }, []);

  const editingReview = (location.state as { fromReview?: boolean } | null)?.fromReview === true;

  const go = useCallback(
    (step: StepId, options: { replace?: boolean; fromReview?: boolean } = {}) => {
      if (step !== "reading" && step !== "done") update({ step });
      void navigate(`/apply/${step}`, { replace: options.replace, state: options.fromReview ? { fromReview: true } : null });
    },
    [navigate, update],
  );

  const forward = useCallback((step: StepId) => go(editingReview ? "review" : step), [go, editingReview]);

  const finish = useCallback(() => {
    finished.current = true;
    if (userId) clearDraft(userId);
    setCover(null);
    setMenus(() => []);
  }, [userId, setCover, setMenus]);

  // Photos are released with the page.
  const photos = useRef({ cover, menus });
  useEffect(() => {
    photos.current = { cover, menus };
  }, [cover, menus]);
  useEffect(
    () => () => {
      if (photos.current.cover) URL.revokeObjectURL(photos.current.cover.previewUrl);
      for (const photo of photos.current.menus) URL.revokeObjectURL(photo.previewUrl);
    },
    [],
  );

  const value = useMemo<Application>(
    () => ({
      draft,
      latest: () => latestDraft.current,
      update,
      cover,
      setCover,
      menus,
      setMenus,
      notices,
      setNotice,
      editingReview,
      go,
      forward,
      finish,
      isAt: (step: StepId) => path.current === `/apply/${step}`,
      reading,
      setReading,
    }),
    [draft, update, cover, setCover, menus, setMenus, notices, setNotice, editingReview, go, forward, finish, reading],
  );
  return <ApplicationContext.Provider value={value}>{children}</ApplicationContext.Provider>;
}

export function useApplication(): Application {
  const application = useContext(ApplicationContext);
  if (!application) throw new Error("useApplication must be used inside ApplicationProvider.");
  return application;
}

