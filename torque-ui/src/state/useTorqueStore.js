import { create } from "zustand";

const useTorqueStore = create((set) => ({
  state: "loading",

  message: "",

  connected: false,

  setState: (state) => set({ state }),

  setMessage: (message) => set({ message }),

  setConnected: (connected) => set({ connected }),
}));

export default useTorqueStore;
