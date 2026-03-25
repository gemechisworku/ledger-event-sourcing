import { create } from 'zustand'

type UiState = {
  selectedStage: string | null
  setSelectedStage: (s: string | null) => void
}

export const useUiStore = create<UiState>((set) => ({
  selectedStage: null,
  setSelectedStage: (s) => set({ selectedStage: s }),
}))
