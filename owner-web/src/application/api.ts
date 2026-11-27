import type { ApiClient } from "../api/client";
import { unwrap } from "../api/client";
import { ApiError } from "../api/errors";
import type { components } from "../api/schema";
import type { PreparedImage } from "../images/prepare";
import type { ApplicationDraft } from "./draft";
import { businessDigits, phoneDigits } from "./rules";

export type CertificateReading = components["schemas"]["BusinessCertificateOcrResponse"];
export type BusinessCheckResult = components["schemas"]["BusinessCheckResponse"]["result"];
export type BarNameItem = components["schemas"]["BarNamesResponse"]["items"][number];
type ApplicationInput = components["schemas"]["ExistingBarApplicationInput"] | components["schemas"]["NewBarApplicationInput"];

/** A multipart body of JPEG images under `field` (the typed client passes FormData through). */
export function imageForm(field: string, images: readonly PreparedImage[]): FormData {
  const form = new FormData();
  for (const image of images) form.append(field, new File([image.blob], image.fileName, { type: "image/jpeg" }));
  return form;
}

/** POST /api/owner-applications/business-certificate-ocr (spec 3.11.12): values to prefill, never stored. */
export async function readCertificate(api: ApiClient, image: PreparedImage): Promise<CertificateReading> {
  return unwrap(
    await api.POST("/api/owner-applications/business-certificate-ocr", { body: imageForm("image", [image]) as never }),
  );
}

/** POST /api/owner-applications/business-verification (spec 3.11.16). */
export async function checkBusiness(
  api: ApiClient,
  fields: Pick<ApplicationDraft, "businessNumber" | "representativeName" | "openingDate">,
): Promise<BusinessCheckResult> {
  const response = unwrap(
    await api.POST("/api/owner-applications/business-verification", {
      body: {
        businessRegistrationNumber: businessDigits(fields.businessNumber),
        representativeName: fields.representativeName.trim(),
        openingDate: fields.openingDate,
      },
    }),
  );
  return response.result;
}

/** GET /api/search/bar-names (spec 3.11.11): active bars whose name or address contains the query. */
export async function searchBarNames(api: ApiClient, query: string, signal?: AbortSignal): Promise<BarNameItem[]> {
  return unwrap(await api.GET("/api/search/bar-names", { params: { query: { query, limit: 20 } }, signal })).items;
}

/** The request body of POST /api/owner-applications for the draft (spec 3.11.2). */
export function applicationInput(draft: ApplicationDraft): ApplicationInput {
  const business = {
    businessRegistrationNumber: businessDigits(draft.businessNumber),
    representativeName: draft.representativeName.trim(),
    openingDate: draft.openingDate,
    contactPhone: phoneDigits(draft.contactPhone),
    contactPhonePublic: draft.contactPhonePublic,
  };
  if (draft.kind === "existing_bar" && draft.existingBar) {
    return { applicationType: "existing_bar", barId: draft.existingBar.barId, ...business };
  }
  return {
    applicationType: "new_bar",
    proposedBar: {
      name: draft.proposedBarName.trim(),
      address: [draft.address, draft.addressDetail].map((part) => part.trim()).filter(Boolean).join(" "),
      phone: draft.storePhone ? phoneDigits(draft.storePhone) : null,
    },
    ...business,
  };
}

export type SubmitStage = "create" | "cover" | "menus";

/** A failed submission step; the application exists from "cover" on, so only the uploads are retried. */
export class SubmitError extends Error {
  readonly stage: SubmitStage;
  readonly cause: unknown;
  constructor(stage: SubmitStage, cause: unknown) {
    super(cause instanceof Error ? cause.message : String(cause));
    this.name = "SubmitError";
    this.stage = stage;
    this.cause = cause;
  }
}

interface SubmitOptions {
  api: ApiClient;
  draft: ApplicationDraft;
  cover: PreparedImage | null;
  menus: readonly PreparedImage[];
  /** Called as each step succeeds, so the draft remembers it before the next one can fail. */
  onProgress: (progress: Pick<ApplicationDraft, "applicationId" | "uploaded">) => void;
}

/**
 * Sends the application as the app does (android/.../data/owner/LiveOwnerScreenRepository.kt
 * submitRegistrationDraftLive): create it (3.11.2), then a new bar's cover photo (3.11.17), then the menu
 * photos (3.11.15). After a failed upload the application is not created again: the next attempt only
 * uploads what is left, for the same applicationId.
 */
export async function submitApplication({ api, draft, cover, menus, onProgress }: SubmitOptions): Promise<string> {
  let applicationId = draft.applicationId;
  let uploaded = { ...draft.uploaded };

  if (!applicationId) {
    try {
      applicationId = await createApplication(api, applicationInput(draft));
    } catch (error) {
      throw new SubmitError("create", error);
    }
    uploaded = { cover: false, menus: false };
    onProgress({ applicationId, uploaded });
  }

  if (draft.kind === "new_bar" && cover && !uploaded.cover) {
    try {
      unwrap(
        await api.PUT("/api/owner-applications/{applicationId}/cover-photo", {
          params: { path: { applicationId } },
          body: imageForm("image", [cover]) as never,
        }),
      );
    } catch (error) {
      throw new SubmitError("cover", error);
    }
    uploaded = { ...uploaded, cover: true };
    onProgress({ applicationId, uploaded });
  }

  if (menus.length > 0 && !uploaded.menus) {
    try {
      unwrap(
        await api.PUT("/api/owner-applications/{applicationId}/menu-photos", {
          params: { path: { applicationId } },
          body: imageForm("images", menus) as never,
        }),
      );
    } catch (error) {
      throw new SubmitError("menus", error);
    }
    uploaded = { ...uploaded, menus: true };
    onProgress({ applicationId, uploaded });
  }
  return applicationId;
}

/** Creates the application; a user without a users row is created with GET /api/me, then asked once more. */
async function createApplication(api: ApiClient, body: ApplicationInput): Promise<string> {
  const post = async () => unwrap(await api.POST("/api/owner-applications", { body })).applicationId;
  try {
    return await post();
  } catch (error) {
    if (!(error instanceof ApiError && error.code === "USER_NOT_FOUND")) throw error;
    unwrap(await api.GET("/api/me"));
    return post();
  }
}
