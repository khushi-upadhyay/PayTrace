import { redirect } from "next/navigation";

type LegacyCheckoutProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function LegacyPayPalCheckoutPage({ searchParams }: LegacyCheckoutProps) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(await searchParams)) {
    if (Array.isArray(value)) {
      value.forEach((entry) => params.append(key, entry));
    } else if (value !== undefined) {
      params.set(key, value);
    }
  }
  const query = params.toString();
  redirect(`/checkout${query ? `?${query}` : ""}`);
}
