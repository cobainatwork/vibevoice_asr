import { create } from "zustand";
import type { Project } from "../api/types";
import { projectsApi } from "../api/projects";

interface ProjectStore {
  projects: Project[];
  current: Project | null;
  loading: boolean;
  load: () => Promise<void>;
  setCurrent: (id: number) => Promise<void>;
}

export const useProjectStore = create<ProjectStore>((set) => ({
  projects: [],
  current: null,
  loading: false,

  load: async () => {
    set({ loading: true });
    try {
      const projects = await projectsApi.list();
      set({ projects, loading: false });
    } catch (e) {
      set({ loading: false });
      throw e;
    }
  },

  setCurrent: async (id: number) => {
    const p = await projectsApi.get(id);
    set({ current: p });
  },
}));
