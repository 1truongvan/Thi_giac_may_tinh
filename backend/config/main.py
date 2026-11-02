import tkinter as tk
from tkinter import filedialog, messagebox

# ===== chọn file =====
def select_file():
    file_path = filedialog.askopenfilename(
        filetypes=[("Video files", "*.mp4")]
    )
    if file_path:
        entry_path.delete(0, tk.END)
        entry_path.insert(0, file_path)

# ===== xử lý (chưa code backend) =====
def process_video():
    path = entry_path.get()

    if not path:
        messagebox.showerror("Lỗi", "Chưa chọn video!")
        return

    messagebox.showinfo("Thông báo", "Đã chọn video!\nSẽ xử lý sau 😎")

# ===== UI =====
root = tk.Tk()
root.title("🎥 Video Stabilization App")
root.geometry("600x250")
root.resizable(False, False)

# tiêu đề
title = tk.Label(root, text="Video Stabilization",
                 font=("Arial", 16, "bold"))
title.pack(pady=10)

# input
frame = tk.Frame(root)
frame.pack(pady=10)

entry_path = tk.Entry(frame, width=50)
entry_path.grid(row=0, column=0, padx=5)

btn_browse = tk.Button(frame, text="Browse", command=select_file)
btn_browse.grid(row=0, column=1)

# nút xử lý
btn_process = tk.Button(root,
                        text="Stabilize Video",
                        command=process_video,
                        bg="green",
                        fg="white",
                        font=("Arial", 12))
btn_process.pack(pady=20)

# trạng thái
status_label = tk.Label(root, text="Chưa xử lý", fg="gray")
status_label.pack()

root.mainloop()