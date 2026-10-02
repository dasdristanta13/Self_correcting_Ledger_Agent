import { render } from "@testing-library/react";
import App from "../App";

export function renderAt(hash: string) {
  window.location.hash = hash;
  return render(<App />);
}
