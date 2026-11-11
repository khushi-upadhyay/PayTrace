"use client";

import React, { useMemo, useState } from "react";
import { CreditCard, Loader2, Lock, Minus, Plus, ShoppingCart, Trash2 } from "lucide-react";

export interface CartLine {
  id: string;
  name: string;
  shop_name: string;
  price: number;
  stock: number;
  image_url?: string | null;
  quantity: number;
}

interface Props {
  lines: CartLine[];
  processing: boolean;
  message: string | null;
  onChangeQty: (id: string, qty: number) => void;
  onRemove: (id: string) => void;
  /** Called when the buyer picks a payment method. Card details never leave this component. */
  onPay: (method: "paypal" | "paylater" | "card") => void;
}

const money = (n: number) => `$${n.toFixed(2)}`;

function luhnOk(num: string) {
  const digits = num.replace(/\s/g, "");
  if (!/^\d{13,19}$/.test(digits)) return false;
  let sum = 0;
  let dbl = false;
  for (let i = digits.length - 1; i >= 0; i--) {
    let d = Number(digits[i]);
    if (dbl) {
      d *= 2;
      if (d > 9) d -= 9;
    }
    sum += d;
    dbl = !dbl;
  }
  return sum % 10 === 0;
}

function expiryOk(v: string) {
  const m = /^(\d{2})\s*\/\s*(\d{2})$/.exec(v);
  if (!m) return false;
  const month = Number(m[1]);
  const year = 2000 + Number(m[2]);
  if (month < 1 || month > 12) return false;
  const now = new Date();
  return year > now.getFullYear() || (year === now.getFullYear() && month >= now.getMonth() + 1);
}

function PayPalWordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`font-extrabold italic tracking-tight ${className}`} style={{ fontFamily: "Verdana, Arial, sans-serif" }}>
      <span className="text-[#003087]">Pay</span>
      <span className="text-[#009cde]">Pal</span>
    </span>
  );
}

export default function CartPayment({ lines, processing, message, onChangeQty, onRemove, onPay }: Props) {
  const [cardOpen, setCardOpen] = useState(false);
  const [number, setNumber] = useState("");
  const [expiry, setExpiry] = useState("");
  const [cvv, setCvv] = useState("");
  const [name, setName] = useState("");
  const [zip, setZip] = useState("");
  const [touched, setTouched] = useState(false);

  const count = lines.reduce((n, l) => n + l.quantity, 0);
  const subtotal = useMemo(() => lines.reduce((n, l) => n + l.price * l.quantity, 0), [lines]);

  const errors = {
    number: luhnOk(number) ? "" : "Enter a valid card number",
    expiry: expiryOk(expiry) ? "" : "Enter a valid expiry (MM/YY)",
    cvv: /^\d{3,4}$/.test(cvv) ? "" : "Enter the security code",
    name: name.trim().length >= 2 ? "" : "Enter the name on the card",
    zip: zip.trim().length >= 3 ? "" : "Enter a billing ZIP",
  };
  const cardValid = Object.values(errors).every((e) => !e);

  const submitCard = (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!cardValid || processing) return;
    onPay("card");
  };

  const fieldCls = (err: string) =>
    `w-full rounded-md border bg-white px-3 py-2.5 text-sm text-[#2c2e2f] placeholder-[#9da3a6] focus:outline-none focus:ring-2 focus:ring-[#0070ba]/30 ${
      touched && err ? "border-[#d20000]" : "border-[#9da3a6] focus:border-[#0070ba]"
    }`;

  return (
    <div className="space-y-4">
      {/* Cart */}
      <div className="rounded-2xl border border-[#e2e8f0] bg-white p-5">
        <div className="flex items-center justify-between pb-3 border-b border-[#f1f5f9]">
          <h2 className="text-sm font-bold text-[#0f172a] flex items-center gap-2">
            <ShoppingCart className="w-4 h-4 text-paypal-blue" />
            Your Cart
          </h2>
          <span className="text-[10px] text-[#94a3b8] font-mono">
            {count} {count === 1 ? "item" : "items"}
          </span>
        </div>

        {lines.length === 0 ? (
          <p className="text-xs text-[#94a3b8] text-center py-8">
            Tap <strong>Add to Cart</strong> on a product &mdash; it will appear here with payment options.
          </p>
        ) : (
          <div className="mt-3 space-y-2 max-h-72 overflow-y-auto pr-1">
            {lines.map((l) => (
              <div key={l.id} className="flex items-center gap-3 rounded-xl bg-[#f8fafc] border border-[#e2e8f0] p-2.5 text-xs">
                <div className="min-w-0 flex-1">
                  <span className="font-semibold text-[#0f172a] block truncate">{l.name}</span>
                  <span className="text-[10px] text-[#94a3b8] block truncate">{l.shop_name}</span>
                  <div className="mt-1.5 inline-flex items-center rounded-full border border-[#cbd5e1] bg-white">
                    <button
                      type="button"
                      aria-label={`Decrease quantity of ${l.name}`}
                      onClick={() => onChangeQty(l.id, l.quantity - 1)}
                      disabled={processing}
                      className="p-1.5 text-[#475569] hover:text-[#0f172a] disabled:opacity-40"
                    >
                      <Minus className="h-3 w-3" />
                    </button>
                    <span className="w-6 text-center font-mono text-[11px] font-bold">{l.quantity}</span>
                    <button
                      type="button"
                      aria-label={`Increase quantity of ${l.name}`}
                      onClick={() => onChangeQty(l.id, l.quantity + 1)}
                      disabled={processing || l.quantity >= l.stock}
                      className="p-1.5 text-[#475569] hover:text-[#0f172a] disabled:opacity-40"
                    >
                      <Plus className="h-3 w-3" />
                    </button>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2 shrink-0">
                  <span className="font-mono font-bold text-paypal-navy">{money(l.price * l.quantity)}</span>
                  <button
                    type="button"
                    aria-label={`Remove ${l.name}`}
                    onClick={() => onRemove(l.id)}
                    disabled={processing}
                    className="text-[#94a3b8] hover:text-[#d20000] disabled:opacity-40"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Payment cards, PayPal style */}
      {lines.length > 0 && (
        <div className="rounded-2xl border border-[#e2e8f0] bg-white p-5 space-y-4" aria-label="Payment">
          <div className="space-y-1.5 text-sm text-[#2c2e2f]">
            <div className="flex justify-between">
              <span className="text-[#6c7378]">Items ({count})</span>
              <span>{money(subtotal)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#6c7378]">Shipping</span>
              <span>Free</span>
            </div>
            <div className="flex justify-between border-t border-[#e2e8f0] pt-2 text-base font-bold">
              <span>Total</span>
              <span>{money(subtotal)}</span>
            </div>
          </div>

          <div className="space-y-2.5">
            <button
              type="button"
              onClick={() => onPay("paypal")}
              disabled={processing}
              aria-label="Pay with PayPal"
              className="flex h-[45px] w-full items-center justify-center rounded-[4px] bg-[#ffc439] text-[#2c2e2f] transition hover:brightness-95 disabled:opacity-60"
            >
              {processing ? <Loader2 className="h-5 w-5 animate-spin text-[#003087]" /> : <PayPalWordmark className="text-[22px]" />}
            </button>

            <button
              type="button"
              onClick={() => onPay("paylater")}
              disabled={processing}
              aria-label="PayPal Pay Later"
              className="flex h-[45px] w-full items-center justify-center gap-2 rounded-[4px] bg-[#ffc439] transition hover:brightness-95 disabled:opacity-60"
            >
              <PayPalWordmark className="text-[20px]" />
              <span className="text-[15px] font-bold italic text-[#003087]">Pay Later</span>
            </button>

            <button
              type="button"
              onClick={() => setCardOpen((o) => !o)}
              disabled={processing}
              aria-expanded={cardOpen}
              className="flex h-[45px] w-full items-center justify-center gap-2 rounded-[4px] bg-[#2c2e2f] text-sm font-bold text-white transition hover:bg-black disabled:opacity-60"
            >
              <CreditCard className="h-4 w-4" />
              Debit or Credit Card
            </button>
          </div>

          {cardOpen && (
            <form onSubmit={submitCard} noValidate className="space-y-3 border-t border-[#e2e8f0] pt-4">
              <div>
                <label htmlFor="cc-number" className="mb-1 block text-xs font-semibold text-[#2c2e2f]">Card number</label>
                <input
                  id="cc-number"
                  inputMode="numeric"
                  autoComplete="cc-number"
                  placeholder="1234 5678 9012 3456"
                  value={number}
                  maxLength={23}
                  onChange={(e) => setNumber(e.target.value.replace(/[^\d ]/g, "").replace(/\s+/g, " "))}
                  className={fieldCls(errors.number)}
                />
                {touched && errors.number && <p className="mt-1 text-xs text-[#d20000]">{errors.number}</p>}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="cc-exp" className="mb-1 block text-xs font-semibold text-[#2c2e2f]">Expires</label>
                  <input
                    id="cc-exp"
                    inputMode="numeric"
                    autoComplete="cc-exp"
                    placeholder="MM/YY"
                    value={expiry}
                    maxLength={5}
                    onChange={(e) => {
                      const d = e.target.value.replace(/\D/g, "").slice(0, 4);
                      setExpiry(d.length > 2 ? `${d.slice(0, 2)}/${d.slice(2)}` : d);
                    }}
                    className={fieldCls(errors.expiry)}
                  />
                  {touched && errors.expiry && <p className="mt-1 text-xs text-[#d20000]">{errors.expiry}</p>}
                </div>
                <div>
                  <label htmlFor="cc-cvv" className="mb-1 block text-xs font-semibold text-[#2c2e2f]">CVV</label>
                  <input
                    id="cc-cvv"
                    inputMode="numeric"
                    autoComplete="cc-csc"
                    placeholder="123"
                    value={cvv}
                    maxLength={4}
                    onChange={(e) => setCvv(e.target.value.replace(/\D/g, ""))}
                    className={fieldCls(errors.cvv)}
                  />
                  {touched && errors.cvv && <p className="mt-1 text-xs text-[#d20000]">{errors.cvv}</p>}
                </div>
              </div>
              <div>
                <label htmlFor="cc-name" className="mb-1 block text-xs font-semibold text-[#2c2e2f]">Name on card</label>
                <input
                  id="cc-name"
                  autoComplete="cc-name"
                  placeholder="Full name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className={fieldCls(errors.name)}
                />
                {touched && errors.name && <p className="mt-1 text-xs text-[#d20000]">{errors.name}</p>}
              </div>
              <div>
                <label htmlFor="cc-zip" className="mb-1 block text-xs font-semibold text-[#2c2e2f]">Billing ZIP code</label>
                <input
                  id="cc-zip"
                  autoComplete="postal-code"
                  placeholder="ZIP code"
                  value={zip}
                  onChange={(e) => setZip(e.target.value)}
                  className={fieldCls(errors.zip)}
                />
                {touched && errors.zip && <p className="mt-1 text-xs text-[#d20000]">{errors.zip}</p>}
              </div>
              <button
                type="submit"
                disabled={processing}
                className="flex h-[45px] w-full items-center justify-center gap-2 rounded-[4px] bg-[#0070ba] text-sm font-bold text-white transition hover:bg-[#005ea6] disabled:opacity-60"
              >
                {processing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Lock className="h-3.5 w-3.5" />}
                Pay {money(subtotal)}
              </button>
              <p className="text-center text-[10px] text-[#6c7378]">
                Sandbox demo: card details are validated in your browser and are never stored or sent to our servers.
              </p>
            </form>
          )}

          {message && (
            <p role="status" className="rounded-lg bg-[#f5f7fa] p-3 text-xs text-[#2c2e2f]">
              {message}
            </p>
          )}

          <p className="flex items-center justify-center gap-1.5 text-[11px] text-[#6c7378]">
            <Lock className="h-3 w-3" /> Powered by <PayPalWordmark className="text-[12px]" />
          </p>
        </div>
      )}
    </div>
  );
}
