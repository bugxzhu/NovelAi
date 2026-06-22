import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { DiscussButton } from "@/components/editor/DiscussButton";
import { useDiscussStore } from "@/lib/store";

describe("DiscussButton", () => {
  beforeEach(() => {
    useDiscussStore.setState({ resultByChapter: {}, modalOpenFor: null });
  });

  it("renders button text", () => {
    render(<DiscussButton chapterId={5} />);
    expect(screen.getByText(/探讨/)).toBeTruthy();
  });

  it("opens modal on click", async () => {
    const { getByRole } = render(<DiscussButton chapterId={5} />);
    const { userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    await user.click(getByRole("button", { name: /探讨/ }));
    expect(useDiscussStore.getState().modalOpenFor).toBe(5);
  });
});
