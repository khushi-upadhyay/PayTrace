import { redirect } from "next/navigation";

type LegacyCheckoutProps = {
  searchParams: Record<string, string | string[] | undefined>;
};

export default function LegacyPayPalCheckoutPage({ searchParams }: LegacyCheckoutProps) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (Array.isArray(value)) {
      value.forEach((entry) => params.append(key, entry));
    } else if (value !== undefined) {
      params.set(key, value);
    }
  }
  const query = params.toString();
  redirect(`/checkout${query ? `?${query}` : ""}`);
}
