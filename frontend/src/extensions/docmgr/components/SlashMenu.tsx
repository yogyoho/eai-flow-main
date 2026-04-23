"use client";

import React, {
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import type { Editor } from "@tiptap/react";
import { editorCommands, filterCommands, type CommandItem } from "../utils/editorCommands";
import { SlashCommandPluginKey, type SlashCommandPluginState } from "../extensions/SlashCommand";
import { getSlashMenuViewportPosition } from "../utils/slashMenuPosition";
import { cn } from "@/lib/utils";

export interface SlashMenuRef {
  onActivate: (state: SlashCommandPluginState) => void;
}

interface SlashMenuProps {
  editor: Editor | null;
  visible: boolean;
  position: { top: number; left: number };
  query: string;
  onClose: () => void;
  onCommand: (item: CommandItem) => void;
}

const SlashMenu = React.forwardRef<SlashMenuRef, SlashMenuProps>(
  ({ editor, visible, position, query, onClose, onCommand }, _ref) => {
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [computedPosition, setComputedPosition] = useState(position);
    const menuRef = useRef<HTMLDivElement>(null);
    const itemsRef = useRef<(HTMLButtonElement | null)[]>([]);

    const filteredItems = filterCommands(query);

    const selectItem = useCallback(
      (index: number) => {
        const item = filteredItems[index];
        if (!item) return;

        onCommand(item);
        onClose();
      },
      [filteredItems, onCommand, onClose]
    );

    useEffect(() => {
      setSelectedIndex(0);
    }, [query]);

    useEffect(() => {
      setComputedPosition(position);
    }, [position]);

    useEffect(() => {
      if (!visible) return;

      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          setSelectedIndex((prev) =>
            prev + 1 < filteredItems.length ? prev + 1 : prev
          );
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          setSelectedIndex((prev) => (prev - 1 >= 0 ? prev - 1 : prev));
        } else if (e.key === "Enter") {
          e.preventDefault();
          selectItem(selectedIndex);
        } else if (e.key === "Escape") {
          e.preventDefault();
          onClose();
        }
      };

      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }, [visible, filteredItems.length, selectedIndex, selectItem, onClose]);

    useEffect(() => {
      if (selectedIndex >= 0 && itemsRef.current[selectedIndex]) {
        itemsRef.current[selectedIndex]?.scrollIntoView({
          block: "nearest",
        });
      }
    }, [selectedIndex]);

    useLayoutEffect(() => {
      if (!visible || !menuRef.current) return;

      const menuRect = menuRef.current.getBoundingClientRect();
      const nextPosition = getSlashMenuViewportPosition(
        position,
        { width: menuRect.width, height: menuRect.height },
        { width: window.innerWidth, height: window.innerHeight }
      );

      if (
        nextPosition.top !== computedPosition.top ||
        nextPosition.left !== computedPosition.left
      ) {
        setComputedPosition(nextPosition);
      }
    }, [visible, position, query, filteredItems.length, computedPosition.top, computedPosition.left]);

    useEffect(() => {
      const handleClickOutside = (e: MouseEvent) => {
        if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
          onClose();
        }
      };

      if (visible) {
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
      }
    }, [visible, onClose]);

    useImperativeHandle(_ref, () => ({
      onActivate: (_state: SlashCommandPluginState) => {},
    }));

    if (!visible) return null;
    const menu = (
      <div
        ref={menuRef}
        className="notion-slash-menu"
        style={{
          position: "fixed",
          top: computedPosition.top,
          left: computedPosition.left,
          zIndex: 9999,
        }}
      >
        <div className="notion-slash-menu-header">
          <span className="notion-slash-menu-title">插入块</span>
        </div>
        <div className="notion-slash-menu-scroll">
          {filteredItems.length === 0 ? (
            <div className="notion-slash-menu-empty">没有找到匹配的命令</div>
          ) : (
            editorCommands.map((group) => {
              const groupItems = filteredItems.filter((item) =>
                group.items.some((gi) => gi.title === item.title)
              );
              if (groupItems.length === 0) return null;

              return (
                <div key={group.title} className="notion-slash-menu-group">
                  <div className="notion-slash-menu-group-title">
                    {group.title}
                  </div>
                  {groupItems.map((item) => {
                    const currentIndex = filteredItems.indexOf(item);
                    const refCallback = (el: HTMLButtonElement | null) => {
                      itemsRef.current[currentIndex] = el;
                    };

                    return (
                      <button
                        key={item.title}
                        ref={refCallback}
                        className={cn(
                          "notion-slash-menu-item",
                          currentIndex === selectedIndex && "selected"
                        )}
                        onClick={() => selectItem(currentIndex)}
                        onMouseEnter={() => setSelectedIndex(currentIndex)}
                      >
                        <div className="notion-slash-menu-item-icon">
                          <span className="notion-slash-menu-item-icon-text">
                            {item.icon}
                          </span>
                        </div>
                        <div className="notion-slash-menu-item-content">
                          <span className="notion-slash-menu-item-title">
                            {item.title}
                          </span>
                          <span className="notion-slash-menu-item-desc">
                            {item.description}
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>
      </div>
    );

    return typeof document !== "undefined" ? createPortal(menu, document.body) : menu;
  }
);

SlashMenu.displayName = "SlashMenu";

export default SlashMenu;
