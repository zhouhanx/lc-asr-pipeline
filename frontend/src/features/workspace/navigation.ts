import {
  Bot,
  Boxes,
  FileClock,
  FileUp,
  Globe2,
  LayoutDashboard,
  ListTodo,
  Settings,
  ShieldCheck,
  Users,
  type LucideIcon,
} from 'lucide-react'

export type NavigationItem = {
  id: string
  label: string
  description: string
  permission: string
  icon: LucideIcon
  badge?: string
}

export type NavigationGroup = {
  label: string
  items: NavigationItem[]
}

export const navigationGroups: NavigationGroup[] = [
  {
    label: '工作台',
    items: [
      {
        id: 'overview',
        label: '总览',
        description: '租户、任务与服务运行状态',
        permission: 'workspace:read',
        icon: LayoutDashboard,
      },
      {
        id: 'submit',
        label: '提交转写',
        description: '上传录音并创建独立任务',
        permission: 'jobs:read',
        icon: FileUp,
      },
      {
        id: 'models',
        label: '模型',
        description: '本地模型和推理配置',
        permission: 'models:read',
        icon: Boxes,
      },
      {
        id: 'agents',
        label: 'Agent 工作流',
        description: 'LangChain 与 LangGraph 编排',
        permission: 'agents:read',
        icon: Bot,
        badge: 'BETA',
      },
    ],
  },
  {
    label: '工作空间',
    items: [
      {
        id: 'tasks',
        label: '转写任务',
        description: '逐个录音监测任务进度',
        permission: 'jobs:read',
        icon: ListTodo,
      },
      {
        id: 'history',
        label: '历史文件',
        description: '复用文件并选择其他模型解析',
        permission: 'jobs:read',
        icon: FileClock,
      },
      {
        id: 'public-tasks',
        label: '公开任务',
        description: '查看所有组织公开的转写内容',
        permission: 'workspace:read',
        icon: Globe2,
      },
    ],
  },
  {
    label: '租户管理',
    items: [
      {
        id: 'members',
        label: '成员',
        description: '租户成员与邀请',
        permission: 'members:read',
        icon: Users,
      },
      {
        id: 'roles',
        label: '角色与权限',
        description: 'RBAC 角色授权',
        permission: 'roles:read',
        icon: ShieldCheck,
      },
      {
        id: 'settings',
        label: '设置',
        description: '租户与安全设置',
        permission: 'tenant:read',
        icon: Settings,
      },
    ],
  },
]

export const allNavigationItems = navigationGroups.flatMap((group) => group.items)
