import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

window.scrollTo = vi.fn();   // jsdom does not implement it; the shell scrolls to top on route change

afterEach(() => cleanup());
