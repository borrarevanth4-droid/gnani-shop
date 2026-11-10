"use client";

import { useEffect, useState } from "react";
import { addCartItem, fetchCart, fetchCategories, fetchProducts, initiateCheckout, removeCartItem } from "@/lib/api";
import { getOrCreateSessionId, SESSION_STORAGE_KEY } from "@/lib/checkout";
import type { Cart, Category, PaymentInfo, Product } from "@/lib/types";
import CategoryTabs from "@/components/CategoryTabs";
import SearchBox from "@/components/SearchBox";
import ProductGrid from "@/components/ProductGrid";
import ProductDetailModal from "@/components/ProductDetailModal";
import CartSidebar from "@/components/CartSidebar";
import PaymentSheet from "@/components/PaymentSheet";
import RequireAuth from "@/components/RequireAuth";
import VoiceAssistant from "@/components/voice/VoiceAssistant";

export default function Home() {
  return (
    <RequireAuth allow={["buyer"]}>
      <Shop />
    </RequireAuth>
  );
}

function Shop() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [addingSku, setAddingSku] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [viewingProduct, setViewingProduct] = useState<Product | null>(null);
  const [buyingNow, setBuyingNow] = useState(false);
  const [payment, setPayment] = useState<PaymentInfo | null>(null);

  function refreshCart() {
    fetchCart().then(setCart).catch((e) => setError(e.message));
  }

  useEffect(() => {
    fetchCategories().then(setCategories).catch((e) => setError(e.message));
    refreshCart();
  }, []);

  useEffect(() => {
    const handle = setTimeout(() => {
      setLoading(true);
      fetchProducts({ category: selectedCategory, search, pageSize: 60 })
        .then((res) => {
          setProducts(res.items);
          setError(null);
        })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(handle);
  }, [selectedCategory, search]);

  async function handleAdd(sku: string) {
    setAddingSku(sku);
    try {
      setCart(await addCartItem(sku));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAddingSku(null);
    }
  }

  async function handleRemove(itemId: number) {
    setRemovingId(itemId);
    try {
      setCart(await removeCartItem(itemId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRemovingId(null);
    }
  }

  async function handleBuyNow() {
    setBuyingNow(true);
    setError(null);
    try {
      setPayment(await initiateCheckout(getOrCreateSessionId()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBuyingNow(false);
    }
  }

  function currentSessionId(): string | null {
    try {
      return window.localStorage.getItem(SESSION_STORAGE_KEY);
    } catch {
      return null;
    }
  }

  return (
    <div className="flex w-full flex-col">
      {/* Chapter 1 — the voice assistant (dark band) */}
      <VoiceAssistant onCart={setCart} onPaid={refreshCart} />

      {/* Chapter 2 — shopping (light band) */}
      <section className="band-light">
        <div className="mx-auto max-w-[1280px] px-4 py-16 sm:px-6 lg:py-24">
          <h2 className="display text-[35px] text-ink sm:text-[44px]">Or browse the shelves</h2>
          <p className="mt-2 max-w-xl text-[17px] text-ink-soft">
            Search in any language — ఆట్టా, दूध, நெய், aata — the same products come up.
          </p>
          {error && <div className="mt-6 rounded-md bg-danger-soft px-4 py-3 text-sm text-danger">{error}</div>}
          <div className="mt-10 grid grid-cols-1 gap-8 lg:grid-cols-[1fr_340px]">
            <main className="flex flex-col gap-6">
              <SearchBox value={search} onChange={setSearch} />
              <CategoryTabs categories={categories} selected={selectedCategory} onSelect={setSelectedCategory} />
              <ProductGrid products={products} onAdd={handleAdd} onView={setViewingProduct} addingSku={addingSku} loading={loading} />
            </main>
            <div className="lg:sticky lg:top-20 lg:self-start">
              <CartSidebar cart={cart} onRemove={handleRemove} removingId={removingId} onBuyNow={handleBuyNow} buyingNow={buyingNow} />
            </div>
          </div>
        </div>
      </section>

      {/* Chapter 3 — how it works (dark band) */}
      <section className="band-night">
        <div className="mx-auto max-w-[1280px] px-4 py-16 sm:px-6 lg:py-24">
          <h2 className="display text-[35px] text-white sm:text-[44px]">Every request runs the same loop</h2>
          <p className="mt-2 max-w-2xl text-[17px] text-on-night-soft">
            Open “Harness loop” under any reply to see these steps for that exact turn.
          </p>
          <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Gnani hears", "Prisma v3.0 turns speech into text and names the language — Telugu, Tamil, Hinglish and 7 more."],
              ["The AI suggests", "The shop assistant proposes one step at a time: search, add to cart, ask to pay. It can't execute anything."],
              ["The rulebook decides", "Plain code checks the real price, stock, your budget and limits: allow, ask you, or refuse — with a reason."],
              ["You tap to pay", "Money only moves on your tap — Wallet or Cash on Delivery. Gnani Timbre reads the total back in your language."],
            ].map(([title, body], i) => (
              <div key={title} className="rounded-md bg-night-card p-6">
                <p className="font-mono text-sm text-link-night">0{i + 1}</p>
                <p className="display mt-3 text-[22px] text-white">{title}</p>
                <p className="mt-2 text-[15px] leading-relaxed text-on-night-soft">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {viewingProduct && (
        <ProductDetailModal
          product={viewingProduct}
          sessionId={currentSessionId()}
          onClose={() => setViewingProduct(null)}
          onAdd={async (sku) => {
            await handleAdd(sku);
            setViewingProduct(null);
          }}
          adding={addingSku === viewingProduct.sku}
        />
      )}

      {payment && (
        <PaymentSheet
          payment={payment}
          onClose={() => {
            setPayment(null);
            refreshCart();
          }}
          onDone={() => refreshCart()}
        />
      )}
    </div>
  );
}
