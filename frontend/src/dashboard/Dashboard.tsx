import { useCallback, useEffect, useRef, useState } from "react";
import GridLayout from "react-grid-layout";
import { useLayoutStore } from "@/store/layout";
import { useUiStore } from "@/store/ui";
import { getWidgetDef } from "@/widgets/registry";
import type { LayoutItem } from "@/types/widget";

const ROW_HEIGHT = 60;
const COLS = 24;

export function Dashboard() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const instances = useLayoutStore((s) => s.instances);
  const gridLayout = useLayoutStore((s) => s.gridLayout);
  const setGridLayout = useLayoutStore((s) => s.setGridLayout);
  const removeWidget = useLayoutStore((s) => s.removeWidget);
  const saveLayout = useLayoutStore((s) => s.saveLayout);
  const isEditMode = useUiStore((s) => s.isEditMode);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const updateWidth = () => setWidth(container.clientWidth);
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const handleLayoutChange = useCallback(
    (newLayout: LayoutItem[]) => {
      setGridLayout(newLayout);
    },
    [setGridLayout]
  );

  const handleDragStop = useCallback(() => {
    void saveLayout();
  }, [saveLayout]);

  const handleResizeStop = useCallback(() => {
    void saveLayout();
  }, [saveLayout]);

  return (
    <div ref={containerRef} className="w-full">
      {!instances.length ? (
        <div className="flex flex-col items-center justify-center h-64 gap-3 text-center">
          <p className="text-muted text-sm">No widgets on this dashboard.</p>
          {!isEditMode && (
            <p className="text-muted text-xs">Enable edit mode to add widgets.</p>
          )}
        </div>
      ) : (
        width > 0 && (
          <GridLayout
            className={`layout${isEditMode ? " dashboard-edit-mode" : ""}`}
            layout={gridLayout}
            cols={COLS}
            rowHeight={ROW_HEIGHT}
            width={width}
            isDraggable={isEditMode}
            isResizable={isEditMode}
            resizeHandles={["se"]}
            draggableCancel=".rgl-no-drag"
            onLayoutChange={handleLayoutChange}
            onDragStop={handleDragStop}
            onResizeStop={handleResizeStop}
            margin={[12, 12]}
          >
            {instances.map((instance) => {
              const def = getWidgetDef(instance.widgetId);
              if (!def) return null;
              const Component = def.component;
              return (
                <div
                  key={instance.instanceId}
                  className="bg-surface border border-border rounded-xl overflow-hidden flex flex-col select-none"
                >
                  {isEditMode && (
                    <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-surface2 cursor-move">
                      <span className="text-xs text-muted font-medium">{def.name}</span>
                      <button
                        onClick={() => { removeWidget(instance.instanceId); void saveLayout(); }}
                        className="rgl-no-drag text-muted hover:text-red-400 text-sm leading-none transition-colors"
                      >
                        ×
                      </button>
                    </div>
                  )}
                  <div className="flex-1 min-h-0">
                    <Component
                      instanceId={instance.instanceId}
                      printerId={instance.printerId}
                      config={instance.config}
                      size={instance.size}
                      isEditMode={isEditMode}
                    />
                  </div>
                </div>
              );
            })}
          </GridLayout>
        )
      )}
    </div>
  );
}
