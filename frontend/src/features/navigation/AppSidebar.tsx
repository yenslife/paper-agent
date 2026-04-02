import { Database, MessageSquareText, UploadCloud } from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";

export type AppView = "chat" | "ingestion" | "papers";

type Props = {
  currentView: AppView;
  onViewChange: (view: AppView) => void;
};

const items: Array<{
  id: AppView;
  label: string;
  description: string;
  icon: typeof MessageSquareText;
}> = [
  {
    id: "chat",
    label: "Paper Agent 聊天",
    description: "和 paper agent 對話、查 abstract 與引用。",
    icon: MessageSquareText,
  },
  {
    id: "ingestion",
    label: "匯入 Paper",
    description: "抓取 Markdown、建立匯入工作並查看進度。",
    icon: UploadCloud,
  },
  {
    id: "papers",
    label: "編輯資料庫內容",
    description: "搜尋、編輯、刪除 paper 與管理 conference 綁定。",
    icon: Database,
  },
];

export function getViewTitle(view: AppView) {
  return items.find((item) => item.id === view)?.label ?? "Paper Agent";
}

export function AppSidebar({ currentView, onViewChange }: Props) {
  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border">
      <SidebarHeader className="gap-0 border-b border-sidebar-border px-3 py-4">
        <div className="px-2">
          <div className="text-xs font-medium uppercase tracking-[0.24em] text-sidebar-foreground/55">
            Workspace
          </div>
          <div className="mt-3 text-base font-semibold tracking-tight text-sidebar-foreground">
            Paper Agent
          </div>
          <p className="mt-1 text-xs leading-5 text-sidebar-foreground/70">
            Research dashboard for chat, ingestion, and paper records.
          </p>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup className="px-3 py-4">
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {items.map((item) => {
                const Icon = item.icon;

                return (
                  <SidebarMenuItem key={item.id}>
                    <SidebarMenuButton
                      isActive={item.id === currentView}
                      tooltip={item.label}
                      className="h-auto min-h-10 rounded-md px-3 py-2.5"
                      onClick={() => onViewChange(item.id)}
                    >
                      <Icon />
                      <div className="min-w-0">
                        <div className="truncate font-medium">{item.label}</div>
                        <div className="mt-0.5 line-clamp-2 text-xs leading-5 text-sidebar-foreground/65">
                          {item.description}
                        </div>
                      </div>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border px-3 py-3">
        <div className="px-2 text-[11px] uppercase tracking-[0.2em] text-sidebar-foreground/50">
          Dashboard
        </div>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
