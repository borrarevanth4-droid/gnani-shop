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
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-6 sm:px-6 sm:py-8">
      <VoiceAssistant onCart={setCart} onPaid={refreshCart} />

      {error && <div className="rounded-lg border border-danger/25 bg-danger-soft px-4 py-3 text-sm text-danger">{error}</div>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <main className="flex flex-col gap-4">
          <SearchBox value={search} onChange={setSearch} />
          <CategoryTabs categories={categories} selected={selectedCategory} onSelect={setSelectedCategory} />
          <ProductGrid products={products} onAdd={handleAdd} onView={setViewingProduct} addingSku={addingSku} loading={loading} />
        </main>

        <div className="lg:sticky lg:top-20 lg:self-start">
          <CartSidebar cart={cart} onRemove={handleRemove} removingId={removingId} onBuyNow={handleBuyNow} buyingNow={buyingNow} />
        </div>
      </div>

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
