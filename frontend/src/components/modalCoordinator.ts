const modalStack: symbol[] = [];
let bodyOverflowBeforeModals = "";

export const registerModal = (id: symbol): void => {
  if (modalStack.length === 0)
    bodyOverflowBeforeModals = document.body.style.overflow;
  modalStack.push(id);
  document.body.style.overflow = "hidden";
};

export const unregisterModal = (id: symbol): void => {
  const stackIndex = modalStack.lastIndexOf(id);
  if (stackIndex >= 0) modalStack.splice(stackIndex, 1);
  if (modalStack.length === 0)
    document.body.style.overflow = bodyOverflowBeforeModals;
};

export const isTopModal = (id: symbol): boolean => modalStack.at(-1) === id;
