import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

const deptState = rs.hoisted(() => ({
  list: rs.fn(),
}));

rs.mock("@/extensions/api", () => ({
  deptApi: { list: deptState.list },
}));

import { DeptAccessPicker } from "@/app/knowledge/_components/DeptAccessPicker";

const DEPARTMENTS = [
  { id: "d1", name: "采矿设计院", sort_order: 1 },
  { id: "d2", name: "机电设计院", sort_order: 2 },
  {
    id: "d3",
    name: "机电设计院-电气",
    sort_order: 3,
    children: [{ id: "d4", name: "电气一组", sort_order: 4 }],
  },
];

afterEach(cleanup);
afterEach(() => {
  rs.restoreAllMocks();
});

describe("DeptAccessPicker", () => {
  it("admin: 勾选部门复选框触发 onChange(['d1'])", async () => {
    deptState.list.mockResolvedValue({ departments: DEPARTMENTS });
    const onChange = rs.fn();
    render(<DeptAccessPicker selectedIds={[]} onChange={onChange} />);

    // 加载完成后渲染内联勾选面板
    const checkbox = await screen.findByRole("checkbox", {
      name: "采矿设计院",
    });
    fireEvent.click(checkbox);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(["d1"]);
  });

  it("admin 已选: 点击标签移除按钮触发 onChange([])", async () => {
    deptState.list.mockResolvedValue({ departments: DEPARTMENTS });
    const onChange = rs.fn();
    render(<DeptAccessPicker selectedIds={["d2"]} onChange={onChange} />);

    // 标签通过其唯一的移除按钮定位(部门名同时出现在勾选面板 label 中)
    const removeButton = await screen.findByRole("button", {
      name: "移除 机电设计院",
    });
    expect(removeButton.closest("span")?.textContent).toContain("机电设计院");
    fireEvent.click(removeButton);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("readOnly: 只渲染标签,无勾选面板、无 role=checkbox", async () => {
    deptState.list.mockResolvedValue({ departments: DEPARTMENTS });
    const onChange = rs.fn();
    render(
      <DeptAccessPicker selectedIds={["d1"]} onChange={onChange} readOnly />,
    );

    expect(await screen.findByText("采矿设计院")).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("readOnly 且未加入部门: 渲染提示文案", async () => {
    deptState.list.mockResolvedValue({ departments: DEPARTMENTS });
    const onChange = rs.fn();
    render(<DeptAccessPicker selectedIds={[]} onChange={onChange} readOnly />);

    expect(await screen.findByText("你尚未加入任何部门")).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("子部门: 拍平后可勾选,标签显示名称而非裸 id", async () => {
    deptState.list.mockResolvedValue({ departments: DEPARTMENTS });

    // 树形响应中的子部门(d4,嵌套在 d3 下)被拍平为可勾选项
    const onChange = rs.fn();
    const { unmount } = render(
      <DeptAccessPicker selectedIds={[]} onChange={onChange} />,
    );
    const childCheckbox = await screen.findByRole("checkbox", {
      name: "电气一组",
    });
    fireEvent.click(childCheckbox);
    expect(onChange).toHaveBeenCalledWith(["d4"]);
    unmount();

    // 子部门标签显示名称而非裸 UUID
    render(<DeptAccessPicker selectedIds={["d4"]} onChange={rs.fn()} />);
    const removeButton = await screen.findByRole("button", {
      name: "移除 电气一组",
    });
    expect(removeButton.closest("span")?.textContent).toContain("电气一组");
    expect(screen.queryByText("d4")).toBeNull();
  });
});
