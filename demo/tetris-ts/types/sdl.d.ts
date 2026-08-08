/**
 * @kmamal/sdl 最小类型声明（官方无 .d.ts）。
 * 仅声明 tetris-ts 用到的 API；其余保持 any。
 */

declare module "@kmamal/sdl" {
  interface Window {
    pixelWidth: number;
    pixelHeight: number;
    on(event: string, listener: (...args: never[]) => void): this;
    render(width: number, height: number, stride: number,
           format: string, buffer: Buffer): void;
    setTitle(title: string): void;
    destroy(): void;
  }

  interface SDL {
    video: {
      createWindow(options: { title: string; width: number; height: number }): Window;
    };
    keyboard: {
      SCANCODE: Record<string, number>;
    };
  }

  const sdl: SDL;
  export default sdl;
}
