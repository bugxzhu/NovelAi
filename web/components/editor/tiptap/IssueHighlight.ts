import { Mark, mergeAttributes } from "@tiptap/core";

export type Severity = "error" | "warn" | "info";

export interface IssueHighlightAttrs {
  issueId: string;
  severity: Severity;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    issueHighlight: {
      setIssueHighlight: (
        attrs: IssueHighlightAttrs,
        from: number,
        to: number,
      ) => ReturnType;
      unsetAllIssueHighlights: () => ReturnType;
    };
  }
}

const SEVERITY_CLASS: Record<Severity, string> = {
  error: "bg-red-300/50",
  warn: "bg-yellow-300/50",
  info: "bg-blue-300/50",
};

export const IssueHighlight = Mark.create({
  name: "issueHighlight",

  inclusive: false,

  addAttributes() {
    return {
      issueId: { default: null },
      severity: { default: "info" },
    };
  },

  parseHTML() {
    return [{ tag: "mark[data-issue-id]" }];
  },

  renderHTML({ HTMLAttributes }) {
    const severity = (HTMLAttributes.severity as Severity) || "info";
    return [
      "mark",
      mergeAttributes(HTMLAttributes, {
        "data-issue-id": HTMLAttributes.issueId,
        class: SEVERITY_CLASS[severity],
      }),
      0,
    ];
  },

  addCommands() {
    return {
      setIssueHighlight:
        (attrs, from, to) =>
        ({ editor }) => {
          editor.commands.setTextSelection({ from, to });
          editor.commands.setMark(this.name, attrs);
          return true;
        },
      unsetAllIssueHighlights:
        () =>
        ({ tr, state }) => {
          const { doc } = state;
          doc.descendants((node, pos) => {
            node.marks.forEach((mark) => {
              if (mark.type.name === this.name) {
                tr.removeMark(pos, pos + node.nodeSize, mark.type);
              }
            });
            return true;
          });
          return true;
        },
    };
  },
});
