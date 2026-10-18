import type { TreasureIslandHandle, TreasureIslandProps } from '@/types/treasureIsland'
export interface TreasureIslandModule {
  mount(container: HTMLElement, props: TreasureIslandProps): TreasureIslandHandle
}
export async function loadTreasureIsland(): Promise<TreasureIslandModule> {
  const entry = `${import.meta.env.BASE_URL}treasure-island/treasure-island.js`
  return await import(/* @vite-ignore */ entry) as TreasureIslandModule
}
