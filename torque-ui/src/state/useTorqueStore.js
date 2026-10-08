import { create } from "zustand";

const useTorqueStore = create((set) => ({
  state: "idle",

  message: "",

  setState: (state) => set({ state }),

  setMessage: (message) => set({ message }),
}));

export default useTorqueStore;