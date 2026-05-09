import { create } from "zustand";
import { projectsApi } from "../api/projects";
import type { ProjectOut } from "../api/types";

interface ProjectState {
  projects: ProjectOut[];
  loading: boolean;
  loaded: boolean;
  refetch: () => Promise<void>;
  getById: (id: number) => ProjectOut | undefined;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  loading: false,
  loaded: false,
  refetch: async () => {
    if (get().loading) return;
    set({ loading: true });
    try {
      const projects = await projectsApi.list();
      set({ projects, loaded: true });
    } finally {
      set({ loading: false });
    }
  },
  getById: (id) => get().projects.find((p) => p.id === id),
}));
