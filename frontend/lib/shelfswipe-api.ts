/**
 * Dedicated ShelfSwipe API Client
 * Uses NEXT_PUBLIC_API_BASE_URL like the rest of the application.
 */

export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  return (configured && configured.length > 0 ? configured : "http://localhost:8000").replace(
    /\/$/,
    ""
  );
}

const API_PREFIX = "/api/v1/shelfswipe";

export class ShelfSwipeApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ShelfSwipeApiError";
    this.status = status;
    this.detail = detail;
  }
}

function formatDetailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.length > 0) {
    return detail;
  }
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.detail === "string") return obj.detail;
    if (typeof obj.message === "string") return obj.message;
    if (typeof obj.msg === "string") return obj.msg;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          const loc = Array.isArray((item as { loc?: unknown }).loc)
            ? (item as { loc: unknown[] }).loc.join(".")
            : "";
          const msg = String((item as { msg: unknown }).msg);
          return loc ? `${loc}: ${msg}` : msg;
        }
        return JSON.stringify(item);
      })
      .filter(Boolean);
    if (parts.length > 0) return parts.join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getApiBaseUrl()}${API_PREFIX}${path}`;
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Requested-With", "PayTrace");

  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(url, { ...init, headers, credentials: "include" });
  } catch (err: unknown) {
    const reason = err instanceof Error ? err.message : "Network error";
    throw new ShelfSwipeApiError(
      `Unable to connect to PayTrace backend (${getApiBaseUrl()}; ${reason})`,
      0
    );
  }

  if (!res.ok) {
    let detail: unknown = null;
    let message = res.statusText || `HTTP ${res.status}`;
    try {
      const data = await res.json();
      detail = data.detail ?? data;
      message = formatDetailMessage(detail, message);
    } catch {
      // not json
    }
    throw new ShelfSwipeApiError(message, res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

export interface DemoShopItem {
  id: string;
  name: string;
  url: string;
  description?: string;
  item_count?: number;
}

export interface ShelfSwipeOnboardRequest {
  shop_url: string;
  consent: boolean;
  seller_name?: string;
  provider: "fixture" | "channel3";
  product_urls?: string[];
  ownership_attested: boolean;
}

export interface ShelfSwipeOnboardResponse {
  seller_id: string;
  shop_id: string;
  job_id: string;
  products_created: number;
  products_skipped: number;
}

export interface ShelfSwipeDraftProductItem {
  id: string;
  external_id: string;
  name: string;
  price: number;
  currency: string;
  image_url: string | null;
  description: string;
  category: string;
  tags: string[];
  stock: number;
  status: "draft" | "live" | string;
  data_source: "demo" | "channel3" | "manual" | string;
  source_url: string | null;
  provider_ref: string | null;
  review_flags: string[];
}

export interface ShelfSwipeDraftResponse {
  seller_id: string;
  shop_id: string;
  name: string;
  description: string | null;
  latitude: number | null;
  longitude: number | null;
  pickup_notes: string | null;
  is_demo: boolean;
  products: ShelfSwipeDraftProductItem[];
}

export interface ProductPatchRequest {
  name?: string;
  price?: number;
  description?: string;
  category?: string;
  tags?: string[];
  image_url?: string | null;
  stock?: number;
}

export interface ProductCreateRequest {
  name: string;
  price: number;
  description?: string;
  category?: string;
  tags?: string[];
  image_url?: string | null;
  stock?: number;
}

export interface ShopPatchRequest {
  pickup_notes?: string;
  latitude?: number;
  longitude?: number;
}

export interface ApproveItem {
  product_id: string;
  confirmed_stock: number;
}

export interface ApproveRejectedItem {
  id: string;
  reason: string;
}

export interface ApproveResponse {
  approved: string[];
  rejected: ApproveRejectedItem[];
  still_draft_count: number;
}

export const shelfswipeApi = {
  async getDemoShops(): Promise<DemoShopItem[]> {
    // The API names these fields shop_id / shop_name / shop_url / product_count.
    const shops = await request<Array<Record<string, unknown>>>("/demo-shops");
    return shops.map((shop) => ({
      id: String(shop.id ?? shop.shop_id ?? ""),
      name: String(shop.name ?? shop.shop_name ?? "Demo shop"),
      url: String(shop.url ?? shop.shop_url ?? ""),
      description: shop.description ? String(shop.description) : undefined,
      item_count: Number(shop.item_count ?? shop.product_count ?? 0) || undefined,
    }));
  },

  onboardSeller(body: ShelfSwipeOnboardRequest): Promise<ShelfSwipeOnboardResponse> {
    return request<ShelfSwipeOnboardResponse>("/sellers/onboard", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  getSellerDraft(
    sellerId: string,
    status: "draft" | "live" | "all" = "draft"
  ): Promise<ShelfSwipeDraftResponse> {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<ShelfSwipeDraftResponse>(`/sellers/${encodeURIComponent(sellerId)}/draft${qs}`);
  },

  patchShop(sellerId: string, body: ShopPatchRequest): Promise<ShelfSwipeDraftResponse> {
    return request<ShelfSwipeDraftResponse>(`/sellers/${encodeURIComponent(sellerId)}/shop`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },

  patchProduct(
    sellerId: string,
    productId: string,
    body: ProductPatchRequest
  ): Promise<ShelfSwipeDraftProductItem> {
    return request<ShelfSwipeDraftProductItem>(
      `/sellers/${encodeURIComponent(sellerId)}/products/${encodeURIComponent(productId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      }
    );
  },

  createProduct(
    sellerId: string,
    body: ProductCreateRequest
  ): Promise<ShelfSwipeDraftProductItem> {
    return request<ShelfSwipeDraftProductItem>(
      `/sellers/${encodeURIComponent(sellerId)}/products`,
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    );
  },

  approveProducts(
    sellerId: string,
    items: ApproveItem[]
  ): Promise<ApproveResponse> {
    return request<ApproveResponse>(`/sellers/${encodeURIComponent(sellerId)}/approve`, {
      method: "POST",
      body: JSON.stringify({ items }),
    });
  },
};

