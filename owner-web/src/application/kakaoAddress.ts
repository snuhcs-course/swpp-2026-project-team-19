/**
 * Address search for a new bar with the Kakao Maps JavaScript SDK, loaded the way the operator dashboard
 * loads it (backend/app/admin/static/app.js loadKakao), with the key from /owner/config.js. The owner can
 * always type the address instead: when there is no key, the SDK fails, or nothing is found.
 */
export interface AddressResult {
  /** The road address (or the lot address when there is none), sent as proposedBar.address. */
  address: string;
  /** What was found: a place name, or the lot address under a road address. */
  label: string | null;
}

interface KakaoServices {
  Status: { OK: string; ZERO_RESULT: string };
  Geocoder: new () => {
    addressSearch(query: string, callback: (result: GeocoderResult[], status: string) => void): void;
  };
  Places: new () => {
    keywordSearch(query: string, callback: (result: PlaceResult[], status: string) => void): void;
  };
}
interface GeocoderResult {
  address_name: string;
  road_address: { address_name: string } | null;
}
interface PlaceResult {
  place_name: string;
  address_name: string;
  road_address_name: string;
}
interface Kakao {
  maps: { load(callback: () => void): void; services: KakaoServices };
}

declare global {
  interface Window {
    kakao?: Kakao;
  }
}

const SDK_URL = "https://dapi.kakao.com/v2/maps/sdk.js";
const UNAVAILABLE = "주소 검색을 쓸 수 없어요. 주소를 직접 입력해 주세요.";
let loading: Promise<Kakao> | null = null;

function loadKakao(key: string | null): Promise<Kakao> {
  if (!key) return Promise.reject(new Error(UNAVAILABLE));
  loading ??= new Promise<Kakao>((resolve, reject) => {
    const failed = () => reject(new Error(UNAVAILABLE));
    const script = document.createElement("script");
    script.src = `${SDK_URL}?appkey=${encodeURIComponent(key)}&libraries=services&autoload=false`;
    script.onerror = failed;
    script.onload = () => {
      const kakao = window.kakao;
      if (!kakao?.maps) return failed();
      const timer = window.setTimeout(failed, 10000);
      kakao.maps.load(() => {
        window.clearTimeout(timer);
        resolve(kakao);
      });
    };
    document.head.append(script);
  }).catch((error: unknown) => {
    loading = null; // the next search tries again
    throw error;
  });
  return loading;
}

function run<T>(search: (callback: (result: T[], status: string) => void) => void, status: KakaoServices["Status"]) {
  return new Promise<T[]>((resolve, reject) => {
    search((result, code) => {
      if (code === status.OK) resolve(result);
      else if (code === status.ZERO_RESULT) resolve([]);
      else reject(new Error("주소를 찾지 못했어요. 잠시 후 다시 시도하거나 직접 입력해 주세요."));
    });
  });
}

/** Addresses for `query`: by address first, then by place name (a bar's name finds its road address). */
export async function searchAddress(key: string | null, query: string): Promise<AddressResult[]> {
  const { services } = (await loadKakao(key)).maps;
  const byAddress = await run<GeocoderResult>((done) => new services.Geocoder().addressSearch(query, done), services.Status);
  const found: AddressResult[] = byAddress.length
    ? byAddress.map((item) => ({
        address: item.road_address?.address_name || item.address_name,
        label: item.road_address ? item.address_name : null,
      }))
    : (await run<PlaceResult>((done) => new services.Places().keywordSearch(query, done), services.Status)).map((place) => ({
        address: place.road_address_name || place.address_name,
        label: place.place_name,
      }));
  const seen = new Set<string>();
  return found.filter((item) => item.address && !seen.has(item.address) && seen.add(item.address)).slice(0, 10);
}
