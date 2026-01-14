import tkinter as tk
from tkinter import filedialog, messagebox
import cv2  # 引入 OpenCV 进行极速处理
import numpy as np
import os
import PIL.Image

# ================= 补丁代码 =================
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS
# ===========================================

from moviepy.editor import VideoFileClip, VideoClip

def create_full_motion_illusion(video_a_path, video_b_path, output_path):
    try:
        print("-" * 30)
        print(">>> 启动全程动态渲染 (OpenCV 加速版)...")
        
        # 1. 加载资源
        clip_a = VideoFileClip(video_a_path)
        clip_b_raw = VideoFileClip(video_b_path)
        
        # 2. 基础参数
        total_duration = 15.0
        target_fps = 30

        # 3. 预处理 B (仅处理时长循环，尺寸留给核心循环处理)
        # 这样可以避免 MoviePy 的 resize/crop 带来的尺寸预测错误
        if clip_b_raw.duration < total_duration:
            try:
                clip_b = clip_b_raw.loop(duration=total_duration)
            except:
                import moviepy.video.fx.all as vfx_all
                clip_b = vfx_all.loop(clip_b_raw, duration=total_duration)
        else:
            clip_b = clip_b_raw.subclip(0, total_duration)

        # --- OpenCV 辅助函数 (比 NumPy 快 10 倍以上) ---
        def fast_adjust_contrast(img, factor):
            # 公式: pixel * alpha + beta
            # 对比度中心调整: 128 + (pixel - 128) * factor 
            # => pixel * factor + 128 * (1 - factor)
            beta = 128 * (1 - factor)
            return cv2.convertScaleAbs(img, alpha=factor, beta=beta)

        # --- 核心修改：全程动态逻辑 ---
        def make_frame(t):
            # A. 获取 Frame A
            # 使用 min 避免浮点数精度导致的越界
            t_a = min(t % clip_a.duration, clip_a.duration - 0.05)
            try:
                frame_a = clip_a.get_frame(t_a) # 返回的是 RGB numpy array
            except:
                frame_a = clip_a.get_frame(max(0, t_a - 0.1))

            # 获取 A 的尺寸 (Height, Width) 用于强制对齐
            h_a, w_a = frame_a.shape[:2]

            # B. 获取 Frame B
            t_b = min(t, total_duration - 0.05)
            try:
                frame_b_raw = clip_b.get_frame(t_b)
            except:
                frame_b_raw = clip_b.get_frame(max(0, t_b - 0.1))

            # --- 关键修复：强制尺寸对齐 ---
            # 无论 B 是什么尺寸，强制 resize 成 A 的尺寸
            # cv2.resize 接收 (Width, Height)
            if frame_b_raw.shape[:2] != (h_a, w_a):
                frame_b = cv2.resize(frame_b_raw, (w_a, h_a), interpolation=cv2.INTER_LINEAR)
            else:
                frame_b = frame_b_raw

            # === 阶段 1: 封面保护 (0s - 0.2s) ===
            if t < 0.2:
                return frame_a

            # === 阶段 2: 引导段 (0.2s - 4s) ===
            if t < 4.0:
                frame_idx = int(t * target_fps)
                if frame_idx % 2 == 0:
                    return frame_a
                else:
                    # 高速对比度调整
                    b_boosted = fast_adjust_contrast(frame_b, 1.5)
                    # 变暗 40%: cv2.multiply 或 addWeighted
                    # output = b * 0.4 + 0
                    return cv2.addWeighted(b_boosted, 0.4, np.zeros_like(b_boosted), 0, 0)

            # === 阶段 3: 全程动态融合 (4s - 结束) ===
            else:
                # 动态计算对比度
                progress = (t - 4.0) / (total_duration - 4.0)
                contrast = 2.0 + (0.5 * progress) 
                
                # 1. 调整 B 的对比度
                b_boosted = fast_adjust_contrast(frame_b, contrast)
                
                # 2. 混合 A 和 B (各 50%)
                # output = A * 0.5 + B * 0.5 + 0
                return cv2.addWeighted(frame_a, 0.5, b_boosted, 0.5, 0)

        print(f"正在渲染... (OpenCV 极速版 + 自动纠错)")
        final_video = VideoClip(make_frame, duration=total_duration)

        # 音频处理
        if clip_a.audio:
            audio = clip_a.audio
            if audio.duration < total_duration:
                from moviepy.audio.fx.all import audio_loop
                audio = audio_loop(audio, duration=total_duration)
            else:
                audio = audio.subclip(0, total_duration)
            final_video = final_video.set_audio(audio)

        final_video.write_videofile(
            output_path, 
            fps=target_fps, 
            codec="libx264", 
            audio_codec="aac",
            threads=6, 
            preset="ultrafast",  # 保持极速
            ffmpeg_params=["-crf", "23"],
            verbose=False,
            logger='bar'
        )
        
        # 清理资源
        clip_a.close()
        clip_b_raw.close()
        clip_b.close()
        
        return True

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"处理出错: {e}")
        return False

# --- UI 部分 ---
def select_file_gui():
    root = tk.Tk()
    root.withdraw()

    print(">>> 请选择【背景视频】(A)...")
    path_a = filedialog.askopenfilename(filetypes=[("视频", "*.mp4 *.mov *.avi")])
    if not path_a: return

    print(">>> 请选择【隐藏视频】(B)...")
    path_b = filedialog.askopenfilename(filetypes=[("视频", "*.mp4 *.mov *.avi")])
    if not path_b: return

    dir_b = os.path.dirname(path_b)
    name_b = os.path.splitext(os.path.basename(path_b))[0]
    default_name = f"{name_b}_RZ_Motion_Fix.mp4"

    print(f">>> 准备保存: {default_name}")
    path_out = filedialog.asksaveasfilename(defaultextension=".mp4", initialdir=dir_b, initialfile=default_name)
    if not path_out: return

    success = create_full_motion_illusion(path_a, path_b, path_out)
    
    if success:
        messagebox.showinfo("成功", f"渲染完成！\n{os.path.basename(path_out)}")
    else:
        messagebox.showerror("失败", "详情见控制台")

if __name__ == "__main__":
    select_file_gui()