import { redirect } from "next/navigation";

/** The seller base path is the entry point to onboarding; individual seller
 * records are served by the sibling [sellerId] route. */
export default function ShelfSwipeSellerIndexPage() {
  redirect("/shelfswipe/seller-onboarding");
}
