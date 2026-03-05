import { useRef, useEffect, useState, useCallback } from "react";

/**
 * Wraps a horizontally-scrollable container and renders a duplicate
 * scrollbar that sticks to the bottom of the viewport. The mirror
 * scrollbar hides automatically when the real scrollbar is visible.
 */
export default function StickyScrollbar({ children, className = "" }) {
  const containerRef = useRef(null);
  const mirrorRef = useRef(null);
  const sentinelRef = useRef(null);
  const [scrollWidth, setScrollWidth] = useState(0);
  const [clientWidth, setClientWidth] = useState(0);
  const [showMirror, setShowMirror] = useState(true);
  const syncing = useRef(false);

  // Track scroll / client width of the table container
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => {
      setScrollWidth(el.scrollWidth);
      setClientWidth(el.clientWidth);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    const table = el.querySelector("table");
    if (table) ro.observe(table);
    return () => ro.disconnect();
  }, [children]);

  // Hide mirror when the table bottom scrollbar is visible in the viewport
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const io = new IntersectionObserver(
      ([entry]) => setShowMirror(!entry.isIntersecting),
      { threshold: 0 }
    );
    io.observe(sentinel);
    return () => io.disconnect();
  }, []);

  // Sync scroll positions
  const onContainerScroll = useCallback(() => {
    if (syncing.current) return;
    syncing.current = true;
    if (mirrorRef.current && containerRef.current) {
      mirrorRef.current.scrollLeft = containerRef.current.scrollLeft;
    }
    requestAnimationFrame(() => {
      syncing.current = false;
    });
  }, []);

  const onMirrorScroll = useCallback(() => {
    if (syncing.current) return;
    syncing.current = true;
    if (containerRef.current && mirrorRef.current) {
      containerRef.current.scrollLeft = mirrorRef.current.scrollLeft;
    }
    requestAnimationFrame(() => {
      syncing.current = false;
    });
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    const mirror = mirrorRef.current;
    if (!el || !mirror) return;
    el.addEventListener("scroll", onContainerScroll, { passive: true });
    mirror.addEventListener("scroll", onMirrorScroll, { passive: true });
    return () => {
      el.removeEventListener("scroll", onContainerScroll);
      mirror.removeEventListener("scroll", onMirrorScroll);
    };
  }, [onContainerScroll, onMirrorScroll]);

  const needsScroll = scrollWidth > clientWidth;

  return (
    <div>
      <div ref={containerRef} className={className}>
        {children}
      </div>
      {/* Sentinel at the bottom of the table — used to detect visibility */}
      <div
        ref={sentinelRef}
        style={{ height: 0, width: "100%", pointerEvents: "none" }}
      />
      {/* Sticky mirror scrollbar pinned to the bottom of the viewport */}
      {needsScroll && (
        <div
          ref={mirrorRef}
          className="sticky-scroll-mirror"
          style={{
            opacity: showMirror ? 1 : 0,
            pointerEvents: showMirror ? "auto" : "none",
            transition: "opacity 150ms ease",
          }}
        >
          <div style={{ width: scrollWidth, height: 1 }} />
        </div>
      )}
    </div>
  );
}
