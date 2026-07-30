import {
  useEffect,
  useState,
  type FormEvent,
  type JSX,
  type ReactNode,
} from "react";
import { z } from "zod";

const PANEL_KEY = "yume.task-panel.v1";
const MOVE_STEP = 24;
const SIZE_STEP = 40;
const MIN_WIDTH = 280;
const MAX_WIDTH = 720;
const MIN_HEIGHT = 220;
const MAX_HEIGHT = 720;
const DEFAULT_WIDTH = 400;
const DEFAULT_HEIGHT = 320;
const PANEL_MARGIN = 16;

const PanelStateSchema = z
  .object({
    x: z.number().int(),
    y: z.number().int(),
    width: z.number().int().min(MIN_WIDTH).max(MAX_WIDTH),
    height: z.number().int().min(MIN_HEIGHT).max(MAX_HEIGHT),
    collapsed: z.boolean(),
  })
  .strict();

type PanelState = z.infer<typeof PanelStateSchema>;

export interface ChatPanelProps {
  disabled?: boolean;
  transcript?: ReactNode;
  streamingText?: string;
  onSubmit: (task: string) => Promise<void>;
  onReset?: () => Promise<void>;
}

function viewportWidth(): number {
  return typeof window === "undefined" ? DEFAULT_WIDTH : window.innerWidth;
}

function viewportHeight(): number {
  return typeof window === "undefined" ? DEFAULT_HEIGHT : window.innerHeight;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

function maximumPanelWidth(): number {
  return Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, viewportWidth()));
}

function maximumPanelHeight(): number {
  return Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, viewportHeight()));
}

function clampPanelState(state: PanelState): PanelState {
  const width = clamp(state.width, MIN_WIDTH, maximumPanelWidth());
  const height = clamp(state.height, MIN_HEIGHT, maximumPanelHeight());

  return {
    ...state,
    x: clamp(state.x, 0, Math.max(0, viewportWidth() - width)),
    y: clamp(state.y, 0, Math.max(0, viewportHeight() - height)),
    width,
    height,
  };
}

function defaultPanelState(): PanelState {
  const width = clamp(DEFAULT_WIDTH, MIN_WIDTH, maximumPanelWidth());
  const height = clamp(DEFAULT_HEIGHT, MIN_HEIGHT, maximumPanelHeight());

  return {
    x: Math.max(0, viewportWidth() - width - PANEL_MARGIN),
    y: Math.max(0, viewportHeight() - height - PANEL_MARGIN),
    width,
    height,
    collapsed: false,
  };
}

function loadPanel(): PanelState {
  if (typeof window === "undefined") {
    return defaultPanelState();
  }

  try {
    const value = window.localStorage.getItem(PANEL_KEY);
    if (value === null) {
      return defaultPanelState();
    }

    const parsed: unknown = JSON.parse(value);
    const result = PanelStateSchema.safeParse(parsed);
    return result.success ? clampPanelState(result.data) : defaultPanelState();
  } catch {
    return defaultPanelState();
  }
}

function savePanel(state: PanelState): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(PANEL_KEY, JSON.stringify(state));
  } catch {
    // Presentation persistence is optional; keep the task panel usable.
  }
}

export function ChatPanel({
  disabled = false,
  transcript,
  streamingText = "",
  onSubmit,
  onReset = async () => undefined,
}: ChatPanelProps): JSX.Element {
  const [text, setText] = useState("");
  const [panelState, setPanelState] = useState(loadPanel);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const handleResize = (): void => {
      setPanelState((current) => clampPanelState(current));
    };

    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  const updatePanel = (update: (current: PanelState) => PanelState): void => {
    setPanelState((current) => {
      const next = clampPanelState(update(current));
      savePanel(next);
      return next;
    });
  };

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    const task = text.trim();
    if (!task || disabled || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    try {
      await onSubmit(task);
      setText("");
    } catch {
      // Keep the entered task available for a retry without surfacing duplicate UI.
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleCollapsed = (): void => {
    updatePanel((current) => ({ ...current, collapsed: !current.collapsed }));
  };

  return (
    <section
      aria-label="Task Yume"
      className="chat-panel"
      style={{
        position: "absolute",
        left: panelState.x,
        top: panelState.y,
        width: panelState.width,
        height: panelState.collapsed ? "auto" : panelState.height,
      }}
    >
      <header>
        <strong>Task Yume</strong>
        <button
          aria-label={panelState.collapsed ? "Expand task panel" : "Collapse task panel"}
          onClick={toggleCollapsed}
          type="button"
        >
          {panelState.collapsed ? "+" : "−"}
        </button>
      </header>

      {!panelState.collapsed && (
        <>
          <div aria-label="Task panel position and size" role="group">
            <button
              aria-label="Move task panel left"
              onClick={() =>
                updatePanel((current) => ({ ...current, x: current.x - MOVE_STEP }))
              }
              type="button"
            >
              ←
            </button>
            <button
              aria-label="Move task panel right"
              onClick={() =>
                updatePanel((current) => ({ ...current, x: current.x + MOVE_STEP }))
              }
              type="button"
            >
              →
            </button>
            <button
              aria-label="Move task panel up"
              onClick={() =>
                updatePanel((current) => ({ ...current, y: current.y - MOVE_STEP }))
              }
              type="button"
            >
              ↑
            </button>
            <button
              aria-label="Move task panel down"
              onClick={() =>
                updatePanel((current) => ({ ...current, y: current.y + MOVE_STEP }))
              }
              type="button"
            >
              ↓
            </button>
            <button
              aria-label="Decrease task panel size"
              onClick={() =>
                updatePanel((current) => ({
                  ...current,
                  width: current.width - SIZE_STEP,
                  height: current.height - SIZE_STEP,
                }))
              }
              type="button"
            >
              Smaller
            </button>
            <button
              aria-label="Increase task panel size"
              onClick={() =>
                updatePanel((current) => ({
                  ...current,
                  width: current.width + SIZE_STEP,
                  height: current.height + SIZE_STEP,
                }))
              }
              type="button"
            >
              Larger
            </button>
          </div>

          <div aria-live="polite">
            {transcript}
            {streamingText && (
              <p aria-label="Streaming response">{streamingText}</p>
            )}
          </div>

          <form onSubmit={submit}>
            <textarea
              aria-label="Task for Yume"
              disabled={disabled || isSubmitting}
              onChange={(event) => setText(event.target.value)}
              value={text}
            />
            <button disabled={disabled || isSubmitting || !text.trim()} type="submit">
              Send task
            </button>
            <button disabled={disabled || isSubmitting} onClick={() => void onReset()} type="button">
              Reset conversation
            </button>
          </form>
        </>
      )}
    </section>
  );
}
