import { ref } from "vue";

export function useAsyncState<TData>() {
  const data = ref<TData | null>(null);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  async function run(task: () => Promise<TData>): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      data.value = await task();
    } catch (caughtError) {
      error.value = caughtError instanceof Error ? caughtError.message : String(caughtError);
    } finally {
      isLoading.value = false;
    }
  }

  return {
    data,
    error,
    isLoading,
    run,
  };
}
