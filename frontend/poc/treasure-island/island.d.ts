declare module '@treasure-island-poc' {
  export type TreasureIslandProps = import('../../../pipelines/Treasure-Seeking_Mouse/src/island/contract').TreasureIslandProps;
  export type TreasureIslandHandle = import('../../../pipelines/Treasure-Seeking_Mouse/src/island/contract').TreasureIslandHandle;
  export function mount(container: HTMLElement, props: TreasureIslandProps): TreasureIslandHandle;
}
