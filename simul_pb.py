import os
os.environ["PATH"] = os.path.dirname(__file__) + os.pathsep + os.environ["PATH"]
import mpv
import tkinter as tk
from tkinterdnd2 import *
import urllib.parse
import time
import traceback


version = "1.0.0"


class VideoPlayerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simul PB v" + version)

        # メインのPanedWindowを作成
        self.main_paned = tk.PanedWindow(root, orient=tk.VERTICAL, sashwidth=1, showhandle=False)
        self.main_paned.grid(row=0, column=0, columnspan=8, sticky="nsew")

        # rootのグリッド設定
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # 動画プレーヤー用のフレーム
        self.player_frame = tk.Frame(self.main_paned)
        self.main_paned.add(self.player_frame, sticky="nsew", stretch="always")

        # ボタン群用のフレーム
        self.bottom_frame = tk.Frame(self.main_paned, height=180)
        self.bottom_frame.pack_propagate(False)  # サイズを固定
        self.main_paned.add(self.bottom_frame, sticky="sew", stretch="never")

        # PanedWindowの初期分割位置を設定
        self.root.update_idletasks()
        self.main_paned.sash_place(0, 0, self.root.winfo_height() - 280)

        self.players = [None] * 4
        self.video_files = [None] * 4
        self.volume_labels = [None] * 4
        self.progress_sliders = [None] * 4
        self.loop_enabled = False
        self.is_fullscreen = False
        self.playing = False
        self.first_play = [True] * 4
        self.ended = [False] * 4
        self.layout_mode = "1x4"
        self.is_muted = False
        self.previous_volumes = [50] * 4
        self.property_handlers = {i: {} for i in range(4)}  # プロパティハンドラを保存

        # プレーヤーフレームのグリッド設定
        self.player_frame.grid_rowconfigure(0, weight=1)  # プレーヤー行
        self.player_frame.grid_rowconfigure(1, weight=0, minsize=50)  # スライダー行
        for i in range(8):
            if i % 2 == 0:
                self.player_frame.grid_columnconfigure(i, weight=1)  # プレーヤー列
            else:
                self.player_frame.grid_columnconfigure(i, weight=0, minsize=80)  # ボリューム列

        self.create_players()
        self.create_buttons()
        self.create_sliders()
        self.update_progress_id = self.root.after(1000, self.update_progress)
        self.root.bind('<F11>', self.toggle_fullscreen)
        self.root.bind('<Escape>', lambda e: self.root.attributes('-fullscreen', False))

    def create_players(self):
        temp_player = mpv.MPV()
        available_vos = temp_player.vo
        print(f"Available video outputs: {available_vos}")
        temp_player.terminate()

        vo_candidates = ['opengl', 'gpu', 'direct3d', 'win']
        selected_vo = None

        for i in range(4):
            frame = tk.Frame(self.player_frame, width=320, height=240, bg="lightgray", name=f"frame{i}")
            if self.layout_mode == "2x2":
                frame.grid(row=2 * (i // 2), column=2 * (i % 2), columnspan=2, padx=5, pady=5, sticky="nsew")
            else:  # 1x4レイアウト
                frame.grid(row=0, column=2*i, columnspan=2, padx=5, pady=5, sticky="nsew")

            label = tk.Label(frame, text="Drop video here", name=f"label{i}")
            label.pack(expand=True, fill="both")
            label.drop_target_register(DND_FILES)
            label.dnd_bind('<<Drop>>', lambda e, idx=i: self.drop_file(e, idx))

            if selected_vo is None:
                for vo in vo_candidates:
                    try:
                        player = mpv.MPV(vo=vo,
                                       log_handler=self.log_handler,
                                       input_default_bindings=True,
                                       input_vo_keyboard=True,
                                       osc=True,
                                       hwdec='auto',
                                       keep_open='yes',  # 再生終了後もウィンドウを維持
                                       idle=True,        # アイドル状態を許可
                                       hr_seek='yes',    # 高精度シーク
                                       wid=str(int(label.winfo_id())))
                        selected_vo = vo
                        print(f"Successfully created player with vo={vo}")
                        break
                    except Exception as e:
                        print(f"Failed to create player with vo={vo}: {e}")
                        continue

            if selected_vo is None:
                print("Error: No suitable video output found")
                label.config(text="Error: No Video Output")
                continue

            try:
                player = mpv.MPV(vo=selected_vo,
                               log_handler=self.log_handler,
                               input_default_bindings=True,
                               input_vo_keyboard=True,
                               osc=True,
                               hwdec='auto',
                               keep_open='yes',
                               idle=True,
                               hr_seek='yes',
                               wid=str(int(label.winfo_id())))
            except Exception as e:
                print(f"Failed to create player {i}: {e}")
                label.config(text="Error: Player Creation Failed")
                continue

            self.property_handlers[i] = {}
            self.property_handlers[i]['end-file'] = lambda name, value: self.on_end_file(i, value)
            self.property_handlers[i]['eof-reached'] = lambda name, value: self.on_eof_reached(i, value)
            self.property_handlers[i]['idle'] = lambda name, value: self.on_idle(i, value)
            player.observe_property('end-file', self.property_handlers[i]['end-file'])
            player.observe_property('eof-reached', self.property_handlers[i]['eof-reached'])
            player.observe_property('idle', self.property_handlers[i]['idle'])
            self.players[i] = player
            player.pause = True
            player.volume = 50
            player.loop_file = 'no'  # デフォルトでループオフ
            print(f"Player {i} initialized with vo={selected_vo}, loop-file=no")

    def log_handler(self, loglevel, component, message):
        print(f"[mpv {loglevel}] {component}: {message}")

    def reinitialize_player(self, index):
        try:
            if self.players[index]:
                for prop in ['end-file', 'eof-reached', 'idle']:
                    if prop in self.property_handlers[index]:
                        try:
                            self.players[index].unobserve_property(prop, self.property_handlers[index][prop])
                            print(f"Player {index} unobserved property: {prop}")
                        except Exception as e:
                            print(f"Error unobserving {prop} for player {index}: {e}")
                self.players[index].terminate()
                self.players[index] = None
            self.property_handlers[index] = {}
            frame = self.player_frame.nametowidget(f"frame{index}")
            vo_candidates = ['opengl', 'gpu', 'direct3d', 'win']
            for vo in vo_candidates:
                try:
                    self.players[index] = mpv.MPV(wid=str(frame.winfo_id()), vo=vo, log_handler=self.log_handler,
                                                 loglevel='info', keep_open='yes', hwdec='auto',
                                                 demuxer_lavf_o='fps=24')
                    self.property_handlers[index]['end-file'] = lambda name, value: self.on_end_file(index, value)
                    self.property_handlers[index]['eof-reached'] = lambda name, value: self.on_eof_reached(index, value)
                    self.property_handlers[index]['idle'] = lambda name, value: self.on_idle(index, value)
                    self.players[index].observe_property('end-file', self.property_handlers[index]['end-file'])
                    self.players[index].observe_property('eof-reached', self.property_handlers[index]['eof-reached'])
                    self.players[index].observe_property('idle', self.property_handlers[index]['idle'])
                    self.players[index].pause = True
                    self.players[index].volume = 50
                    self.players[index].loop_file = 'inf' if self.loop_enabled else 'no'  # 現在のループ状態を反映
                    print(f"Player {index} reinitialized with vo={vo}, loop-file={'inf' if self.loop_enabled else 'no'}")
                    return True
                except Exception as e:
                    print(f"Failed to reinitialize player {index} with vo={vo}: {e}")
            self.players[index] = None
            try:
                self.player_frame.nametowidget(f"frame{index}.label{index}").config(text="Error: Player Shutdown")
            except KeyError:
                print(f"Warning: Label for player {index} not found")
            return False
        except Exception as e:
            print(f"Error reinitializing player {index}: {e}\n{traceback.format_exc()}")
            self.players[index] = None
            try:
                self.player_frame.nametowidget(f"frame{index}.label{index}").config(text="Error: Player Shutdown")
            except KeyError:
                print(f"Warning: Label for player {index} not found")
            return False

    def on_end_file(self, index, value):
        if not value or self.loop_enabled:
            return

        try:
            player = self.players[index]
            if not player or getattr(player, 'core_shutdown', False):
                return

            # 動画が実際に終了位置に近い場合のみ処理を実行
            try:
                if player.time_pos and player.duration:
                    if player.time_pos < (player.duration - 1.0):  # 終了1秒前までは無視
                        return
            except:
                pass

            print(f"Video {index} end-file detected: {self.video_files[index]}")
            if self.video_files[index]:
                self.ended[index] = True
                player.pause = True
                # プログレスバーを最後まで移動
                try:
                    if player.duration and self.progress_sliders[index]:
                        self.progress_sliders[index].set(player.duration)
                except:
                    pass
                print(f"Video {index} paused at end")
                self.check_all_ended()
        except Exception as e:
            print(f"Error handling end-file for video {index}: {e}\n{traceback.format_exc()}")
            if self.reinitialize_player(index) and self.video_files[index]:
                try:
                    player = self.players[index]
                    player.loadfile(self.video_files[index], pause=True)
                    if not self.loop_enabled:
                        try:
                            if player.duration:
                                player.seek(player.duration - 0.1)
                        except:
                            pass
                except Exception as e:
                    print(f"Error reloading video {index}: {e}")

    def on_eof_reached(self, index, value):
        if not value or self.loop_enabled:
            return

        try:
            player = self.players[index]
            if not player or getattr(player, 'core_shutdown', False):
                return

            # 動画が実際に終了位置に近い場合のみ処理を実行
            try:
                if player.time_pos and player.duration:
                    if player.time_pos < (player.duration - 1.0):  # 終了1秒前までは無視
                        return
            except:
                pass

            print(f"Video {index} eof-reached detected: {self.video_files[index]}")
            if self.video_files[index]:
                self.ended[index] = True
                player.pause = True
                # プログレスバーを最後まで移動
                try:
                    if player.duration and self.progress_sliders[index]:
                        self.progress_sliders[index].set(player.duration)
                except:
                    pass
                print(f"Video {index} paused at end")
                self.check_all_ended()
        except Exception as e:
            print(f"Error handling eof-reached for video {index}: {e}\n{traceback.format_exc()}")
            if self.reinitialize_player(index) and self.video_files[index]:
                try:
                    player = self.players[index]
                    player.loadfile(self.video_files[index], pause=True)
                    if not self.loop_enabled:
                        try:
                            if player.duration:
                                player.seek(player.duration - 0.1)
                        except:
                            pass
                except Exception as e:
                    print(f"Error reloading video {index}: {e}")

    def on_idle(self, index, value):
        if not value or self.loop_enabled:
            return

        try:
            player = self.players[index]
            if not player or getattr(player, 'core_shutdown', False):
                return

            # 動画が実際に終了位置に近い場合のみ処理を実行
            try:
                if player.time_pos and player.duration:
                    if player.time_pos < (player.duration - 1.0):  # 終了1秒前までは無視
                        return
            except:
                pass

            print(f"Video {index} idle detected: {self.video_files[index]}")
            if self.video_files[index]:
                self.ended[index] = True
                player.pause = True
                # プログレスバーを最後まで移動
                try:
                    if player.duration and self.progress_sliders[index]:
                        self.progress_sliders[index].set(player.duration)
                except:
                    pass
                print(f"Video {index} paused at end")
                self.check_all_ended()
        except Exception as e:
            print(f"Error handling idle for video {index}: {e}\n{traceback.format_exc()}")
            if self.reinitialize_player(index) and self.video_files[index]:
                try:
                    player = self.players[index]
                    player.loadfile(self.video_files[index], pause=True)
                    if not self.loop_enabled:
                        try:
                            if player.duration:
                                player.seek(player.duration - 0.1)
                        except:
                            pass
                except Exception as e:
                    print(f"Error reloading video {index}: {e}")

    def check_all_ended(self):
        all_ended = all(self.ended[i] or self.video_files[i] is None for i in range(4))
        if all_ended and self.playing:
            self.playing = False
            self.play_button.config(text="Play All")
            print("All videos ended, button reset to Play All")
            self.ended = [False] * 4

    def drop_file(self, event, index):
        file_path = event.data
        if file_path.startswith('{'):
            file_path = file_path.lstrip('{').split('}')[0]
        file_path = urllib.parse.unquote(file_path)
        file_path = os.path.normpath(file_path)
        if not os.path.exists(file_path):
            print(f"Error: File not found: {file_path}")
            for widget in event.widget.winfo_children():
                widget.config(text="Error: File Not Found")
            return
        if file_path.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.gif')):
            try:
                self.video_files[index] = file_path
                if not self.players[index] or self.players[index].core_shutdown:
                    self.reinitialize_player(index)
                self.players[index].loadfile(file_path)
                time.sleep(0.1)
                self.players[index].pause = True
                self.first_play[index] = True
                self.ended[index] = False
                try:
                    duration = self.players[index].duration
                    if duration:
                        self.progress_sliders[index].config(to=duration, state="normal")
                        self.progress_sliders[index].set(0)
                        print(f"Player {index} progress slider set to duration: {duration}")
                    else:
                        self.progress_sliders[index].config(to=100, state="disabled")
                        print(f"Player {index} progress slider disabled: no duration")
                except Exception as e:
                    print(f"Error setting up progress slider for player {index}: {e}")
                print(f"Loaded video {index}: {file_path}")
                for widget in event.widget.winfo_children():
                    widget.config(text=os.path.basename(file_path))
            except Exception as e:
                print(f"Error loading video {file_path}: {e}\n{traceback.format_exc()}")
                if self.reinitialize_player(index) and self.video_files[index]:
                    try:
                        self.players[index].loadfile(file_path)
                        time.sleep(0.1)
                        self.players[index].pause = True
                        print(f"Video {index} reinitialized and loaded: {file_path}")
                        if self.progress_sliders[index]:
                            duration = self.players[index].duration
                            if duration is not None and duration > 0:
                                self.progress_sliders[index].config(to=duration, state="normal")
                                self.progress_sliders[index].set(0)
                                print(f"Player {index} progress slider set to duration: {duration}")
                            else:
                                self.progress_sliders[index].config(to=100, state="disabled")
                                self.progress_sliders[index].set(0)
                                print(f"Player {index} progress slider disabled: no duration")
                    except Exception as e2:
                        print(f"Failed to load after reinitialization for video {index}: {e2}")
                        for widget in event.widget.winfo_children():
                            widget.config(text="Error: Invalid Video")

    def create_buttons(self):
        self.button_frame = tk.Frame(self.bottom_frame)
        self.button_frame.pack(fill=tk.X, expand=True, pady=1)

        # ボタン用の内部フレーム
        button_inner_frame = tk.Frame(self.button_frame)
        button_inner_frame.pack(anchor="center")

        self.play_button = tk.Button(button_inner_frame, text="Play All", command=self.toggle_play)
        self.play_button.pack(side=tk.LEFT, padx=5)
        reset_button = tk.Button(button_inner_frame, text="Reset", command=self.reset_all)
        reset_button.pack(side=tk.LEFT, padx=5)
        self.loop_button = tk.Button(button_inner_frame, text="Loop Off", command=self.toggle_loop)
        self.loop_button.pack(side=tk.LEFT, padx=5)
        self.layout_button = tk.Button(button_inner_frame, text="Change Layout", command=self.toggle_layout)
        self.layout_button.pack(side=tk.LEFT, padx=5)
        self.mute_button = tk.Button(button_inner_frame, text="Mute", command=self.toggle_mute)
        self.mute_button.pack(side=tk.LEFT, padx=5)

    def create_sliders(self):
        for i in range(4):
            progress_slider = tk.Scale(self.player_frame, from_=0, to=100, orient=tk.HORIZONTAL, length=300, width=10,
                                  showvalue=0, state="disabled", sliderrelief="raised", sliderlength=15,
                                  troughcolor="gray", command=lambda value, idx=i: self.seek_position(value, idx),
                                  name=f"progress_slider{i}")
            progress_slider.set(0)
            volume_frame = tk.Frame(self.player_frame, name=f"volume_frame{i}")
            volume_slider = tk.Scale(volume_frame, from_=0, to=100, orient=tk.HORIZONTAL, length=100, width=10,
                                    showvalue=0, command=lambda value, idx=i: self.set_volume(value, idx), name=f"slider{i}")
            volume_slider.set(50)
            volume_label = tk.Label(volume_frame, text=f"Vol: {volume_slider.get()}", width=8, font=("Arial", 8), anchor="e")
            volume_label.pack(side=tk.LEFT, padx=(2, 5), anchor="center")
            volume_slider.pack(side=tk.LEFT, padx=2, anchor="center")
            if self.layout_mode == "2x2":
                progress_slider.grid(row=2*(i//2)+1, column=2*(i%2), padx=5, pady=5, sticky="ew")
                volume_frame.grid(row=2*(i//2)+1, column=2*(i%2)+1, padx=5, pady=5, sticky="w")
            else:
                progress_slider.grid(row=1, column=2*i, padx=5, pady=(5, 0), sticky="ew")
                volume_frame.grid(row=1, column=2*i+1, padx=5, pady=(5, 0), sticky="w")
            self.progress_sliders[i] = progress_slider
            self.volume_labels[i] = volume_label

    def update_progress(self):
        for i in range(4):
            try:
                player = self.players[i]
                if (player and not getattr(player, 'core_shutdown', False) and
                    self.video_files[i] and not player.pause and not player.idle_active and
                    self.progress_sliders[i]):
                    time_pos = player.time_pos
                    if time_pos is not None:
                        try:
                            current_value = self.progress_sliders[i].get()
                            if abs(current_value - time_pos) > 0.5:  # 0.5秒以上の差がある場合のみ更新
                                self.progress_sliders[i].set(time_pos)
                                print(f"Player {i} progress updated to {time_pos} seconds")
                        except Exception as e:
                            print(f"Error setting progress slider for player {i}: {e}")
            except Exception as e:
                print(f"Error updating progress for player {i}: {e}\n{traceback.format_exc()}")
        self.update_progress_id = self.root.after(1000, self.update_progress)

    def seek_position(self, value, index):
        try:
            player = self.players[index]
            if player and not getattr(player, 'core_shutdown', False) and self.video_files[index]:
                current_pos = player.time_pos
                target_pos = float(value)
                if abs(current_pos - target_pos) > 0.5:  # 0.5秒以上の差がある場合のみシーク
                    player.seek(target_pos, reference="absolute")
                    print(f"Player {index} seek to {target_pos} seconds")
                    self.root.update_idletasks()
        except Exception as e:
            print(f"Error seeking position for player {index}: {e}\n{traceback.format_exc()}")
            if self.reinitialize_player(index) and self.video_files[index]:
                try:
                    self.players[index].loadfile(self.video_files[index])
                    time.sleep(0.1)
                    self.players[index].pause = True
                    self.players[index].seek(float(value), reference="absolute")
                    print(f"Player {index} reinitialized and seek to {value} seconds")
                except Exception as e2:
                    print(f"Failed to seek after reinitialization for player {index}: {e2}")

    def toggle_play(self):
        self.playing = not self.playing
        for i, player in enumerate(self.players):
            if self.video_files[i] is not None and player and not getattr(player, 'core_shutdown', False):
                try:
                    if self.playing:
                        if not player.filename or player.idle_active:
                            player.loadfile(self.video_files[i])
                            time.sleep(0.1)
                            player.pause = True
                            player.seek(0, reference="absolute")
                            self.first_play[i] = True
                            print(f"Video {i} reloaded: {self.video_files[i]}")
                        if self.first_play[i]:
                            player.seek(0, reference="absolute")
                            self.first_play[i] = False
                        player.pause = False
                        self.ended[i] = False
                        print(f"Playing video {i}: {self.video_files[i]}, filename={player.filename}, pause={player.pause}")
                    else:
                        player.pause = True
                        print(f"Paused video {i}: {self.video_files[i]}, filename={player.filename}, pause={player.pause}")
                except Exception as e:
                    print(f"Error toggling play/pause for video {i}: {e}\n{traceback.format_exc()}")
                    if self.reinitialize_player(i) and self.video_files[i]:
                        try:
                            self.players[i].loadfile(self.video_files[i])
                            time.sleep(0.1)
                            self.players[i].pause = True
                            self.players[i].seek(0, reference="absolute")
                            self.first_play[i] = True
                            print(f"Video {i} reinitialized and reloaded: {self.video_files[i]}")
                            if self.playing:
                                self.players[i].pause = False
                                self.ended[i] = False
                                print(f"Playing video {i} after reinitialization: {self.video_files[i]}")
                        except Exception as e2:
                            print(f"Failed to force reload video {i}: {e2}")
        self.play_button.config(text="Pause All" if self.playing else "Play All")

    def reset_all(self):
        for i, player in enumerate(self.players):
            if self.video_files[i] is not None and player and not getattr(player, 'core_shutdown', False):
                try:
                    player.loadfile(self.video_files[i])
                    time.sleep(0.1)
                    player.seek(0, reference="absolute")
                    player.pause = True
                    self.first_play[i] = True
                    self.ended[i] = False
                    print(f"Reset video {i}: {self.video_files[i]}")
                    if self.progress_sliders[i]:
                        duration = player.duration
                        if duration is not None and duration > 0:
                            self.progress_sliders[i].config(to=duration, state="normal")
                            self.progress_sliders[i].set(0)
                            print(f"Player {i} progress slider reset to duration: {duration}")
                        else:
                            self.progress_sliders[i].config(to=100, state="disabled")
                            self.progress_sliders[i].set(0)
                            print(f"Player {i} progress slider disabled: no duration")
                except Exception as e:
                    print(f"Error resetting video {i}: {e}\n{traceback.format_exc()}")
                    if self.reinitialize_player(i) and self.video_files[i]:
                        try:
                            self.players[i].loadfile(self.video_files[i])
                            time.sleep(0.1)
                            self.players[i].pause = True
                            self.players[i].seek(0, reference="absolute")
                            self.first_play[i] = True
                            self.ended[i] = False
                            print(f"Video {i} reinitialized and reset: {self.video_files[i]}")
                            if self.progress_sliders[i]:
                                duration = self.players[i].duration
                                if duration is not None and duration > 0:
                                    self.progress_sliders[i].config(to=duration, state="normal")
                                    self.progress_sliders[i].set(0)
                                    print(f"Player {i} progress slider reset to duration: {duration}")
                                else:
                                    self.progress_sliders[i].config(to=100, state="disabled")
                                    self.progress_sliders[i].set(0)
                                    print(f"Player {i} progress slider disabled: no duration")
                        except Exception as e2:
                            print(f"Failed to reset after reinitialization for video {i}: {e2}")
        if self.playing:
            self.playing = False
            self.play_button.config(text="Play All")

    def toggle_loop(self):
        self.loop_enabled = not self.loop_enabled
        loop_value = "inf" if self.loop_enabled else "no"
        for i, player in enumerate(self.players):
            if player and not getattr(player, 'core_shutdown', False):
                try:
                    player.loop_file = loop_value
                    if not self.loop_enabled and player.idle_active:
                        player.pause = True
                        try:
                            if player.duration:
                                player.seek(player.duration - 0.1)
                        except:
                            pass
                        print(f"Player {i} paused due to loop off")
                except Exception as e:
                    print(f"Error setting loop for player {i}: {e}")
                    if self.reinitialize_player(i):
                        try:
                            self.players[i].loop_file = loop_value
                            if not self.loop_enabled:
                                self.players[i].pause = True
                                try:
                                    if self.players[i].duration:
                                        self.players[i].seek(self.players[i].duration - 0.1)
                                except:
                                    pass
                            print(f"Player {i} reinitialized and loop set to {loop_value}")
                        except Exception as e2:
                            print(f"Failed to set loop after reinitialization for player {i}: {e2}")
        self.loop_button.config(text=f"Loop {'On' if self.loop_enabled else 'Off'}")

    def set_volume(self, value, index):
        try:
            if self.volume_labels[index] and not self.is_muted:
                self.volume_labels[index].config(text=f"Vol: {int(float(value))}")
            player = self.players[index]
            if player and not getattr(player, 'core_shutdown', False) and not self.is_muted:
                player.volume = float(value)
                print(f"Player {index} volume set to {value}")
            else:
                print(f"Player {index} volume not set: {'muted' if self.is_muted else 'no player instance'}")
            self.previous_volumes[index] = float(value)
            self.root.update_idletasks()
        except Exception as e:
            print(f"Error setting volume for player {index}: {e}\n{traceback.format_exc()}")
            if self.reinitialize_player(index) and self.video_files[index]:
                try:
                    self.players[index].volume = float(value) if not self.is_muted else 0
                    if self.volume_labels[index] and not self.is_muted:
                        self.volume_labels[index].config(text=f"Vol: {int(float(value))}")
                    self.previous_volumes[index] = float(value)
                    print(f"Player {index} reinitialized and volume set: {value}")
                except Exception as e2:
                    print(f"Failed to set volume after reinitialization for player {index}: {e2}")

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        for i in range(4):
            try:
                player = self.players[i]
                volume_frame = self.player_frame.nametowidget(f"volume_frame{i}")
                volume_slider = volume_frame.nametowidget(f"slider{i}")
                if self.is_muted:
                    if player and not getattr(player, 'core_shutdown', False):
                        self.previous_volumes[i] = player.volume
                        player.volume = 0
                        time.sleep(0.01)
                        print(f"Player {i} muted, saved volume: {self.previous_volumes[i]}")
                    volume_slider.set(0)
                    if self.volume_labels[i]:
                        self.volume_labels[i].config(text="Vol: 0")
                        print(f"Player {i} label set to Vol: 0")
                else:
                    if player and not getattr(player, 'core_shutdown', False):
                        player.volume = self.previous_volumes[i]
                        time.sleep(0.01)
                        print(f"Player {i} unmuted, restored volume: {self.previous_volumes[i]}")
                    volume_slider.set(self.previous_volumes[i])
                    if self.volume_labels[i]:
                        self.volume_labels[i].config(text=f"Vol: {int(self.previous_volumes[i])}")
                        print(f"Player {i} label restored: Vol: {int(self.previous_volumes[i])}")
                self.root.update_idletasks()
            except Exception as e:
                print(f"Error toggling mute for player {i}: {e}\n{traceback.format_exc()}")
                if self.reinitialize_player(i) and self.video_files[i]:
                    try:
                        self.players[i].volume = 0 if self.is_muted else self.previous_volumes[i]
                        volume_slider.set(0 if self.is_muted else self.previous_volumes[i])
                        if self.volume_labels[i]:
                            self.volume_labels[i].config(text="Vol: 0" if self.is_muted else f"Vol: {int(self.previous_volumes[i])}")
                        print(f"Player {i} reinitialized and mute state set: {'muted' if self.is_muted else f'restored to {self.previous_volumes[i]}'}")
                        self.root.update_idletasks()
                    except Exception as e2:
                        print(f"Failed to set mute state after reinitialization for player {i}: {e2}")
        self.mute_button.config(text="Unmute" if self.is_muted else "Mute")
        print(f"{'Muted' if self.is_muted else 'Unmuted'} all players, restored volumes: {self.previous_volumes if not self.is_muted else []}")

    def toggle_layout(self):
        # レイアウトモードを順番に切り替え
        layout_modes = ["1x4", "1x3", "1x2", "1x1", "2x2"]
        current_index = layout_modes.index(self.layout_mode)
        self.layout_mode = layout_modes[(current_index + 1) % len(layout_modes)]

        # すべての動画フレームを一旦非表示に
        for i in range(4):
            frame = self.player_frame.nametowidget(f"frame{i}")
            frame.grid_remove()
            if self.progress_sliders[i]:
                self.progress_sliders[i].grid_remove()
            volume_frame = self.player_frame.nametowidget(f"volume_frame{i}")
            volume_frame.grid_remove()

        # グリッド設定をリセット
        for i in range(8):
            self.player_frame.grid_rowconfigure(i, weight=0, minsize=0)
            self.player_frame.grid_columnconfigure(i, weight=0, minsize=0)

        # レイアウトモードに応じた配置
        if self.layout_mode == "2x2":
            # 2x2レイアウトの設定
            for i in range(2):
                self.player_frame.grid_rowconfigure(2 * i, weight=1)
                self.player_frame.grid_rowconfigure(2 * i + 1, weight=0, minsize=50)
                self.player_frame.grid_columnconfigure(2 * i, weight=1)
                self.player_frame.grid_columnconfigure(2 * i + 1, weight=0, minsize=160)
            visible_players = 4
            window_size = "760x680"
        elif self.layout_mode == "1x4":
            # 1x4レイアウトの設定
            self.player_frame.grid_rowconfigure(0, weight=1)
            self.player_frame.grid_rowconfigure(1, weight=0, minsize=50)
            for i in range(4):
                self.player_frame.grid_columnconfigure(2 * i, weight=1)
                self.player_frame.grid_columnconfigure(2 * i + 1, weight=0, minsize=160)
            visible_players = 4
            window_size = "1280x400"
        elif self.layout_mode == "1x3":
            # 1x3レイアウトの設定
            self.player_frame.grid_rowconfigure(0, weight=1)
            self.player_frame.grid_rowconfigure(1, weight=0, minsize=50)
            for i in range(3):
                self.player_frame.grid_columnconfigure(2 * i, weight=1)
                self.player_frame.grid_columnconfigure(2 * i + 1, weight=0, minsize=160)
            visible_players = 3
            window_size = "960x400"
        elif self.layout_mode == "1x2":
            # 1x2レイアウトの設定
            self.player_frame.grid_rowconfigure(0, weight=1)
            self.player_frame.grid_rowconfigure(1, weight=0, minsize=50)
            for i in range(2):
                self.player_frame.grid_columnconfigure(2 * i, weight=1)
                self.player_frame.grid_columnconfigure(2 * i + 1, weight=0, minsize=160)
            visible_players = 2
            window_size = "640x400"
        else:  # "1x1"
            # 1x1レイアウトの設定
            self.player_frame.grid_rowconfigure(0, weight=1)
            self.player_frame.grid_rowconfigure(1, weight=0, minsize=50)
            self.player_frame.grid_columnconfigure(0, weight=1)
            self.player_frame.grid_columnconfigure(1, weight=0, minsize=160)
            visible_players = 1
            window_size = "400x400"

        # 表示する動画フレームの配置
        for i in range(visible_players):
            frame = self.player_frame.nametowidget(f"frame{i}")
            progress_slider = self.progress_sliders[i]
            volume_frame = self.player_frame.nametowidget(f"volume_frame{i}")

            if self.layout_mode == "2x2":
                frame.grid(row=2 * (i // 2), column=2 * (i % 2), columnspan=2, padx=5, pady=5, sticky="nsew")
                progress_slider.grid(row=2 * (i // 2) + 1, column=2 * (i % 2), padx=5, pady=5, sticky="ew")
                volume_frame.grid(row=2 * (i // 2) + 1, column=2 * (i % 2) + 1, padx=5, pady=5, sticky="w")
            else:
                frame.grid(row=0, column=2 * i, columnspan=2, padx=5, pady=5, sticky="nsew")
                progress_slider.grid(row=1, column=2 * i, padx=5, pady=(5, 0), sticky="ew")
                volume_frame.grid(row=1, column=2 * i + 1, padx=5, pady=(5, 0), sticky="w")

        # ボタンフレームの再配置
        self.button_frame.pack_forget()
        self.button_frame.pack(fill=tk.X, expand=True, pady=1)

        # ウィンドウサイズの更新
        if not self.is_fullscreen:
            self.root.geometry(window_size)
        # ボタンテキストを更新したい場合
        # self.layout_button.config(text=f"{self.layout_mode} Layout")
        # print(f"Switched to {self.layout_mode} layout")

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes('-fullscreen', self.is_fullscreen)
        if not self.is_fullscreen:
            self.root.geometry("760x680" if self.layout_mode == "2x2" else "1280x400")

    def on_closing(self):
        self.root.after_cancel(self.update_progress_id)
        for i, player in enumerate(self.players):
            if player and not isinstance(player, dict):
                for prop in ['end-file', 'eof-reached', 'idle']:
                    if prop in self.property_handlers[i]:
                        try:
                            player.unobserve_property(prop, self.property_handlers[i][prop])
                        except Exception:
                            pass
                player.terminate()
        self.root.destroy()

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    # 1x4レイアウト用のグリッド設定
    root.grid_rowconfigure(0, weight=1)  # プレーヤー行
    root.grid_rowconfigure(1, weight=0, minsize=50)  # スライダー行
    root.grid_rowconfigure(2, weight=0)  # ボタン行

    # すべての列の重みを明示的に設定
    for i in range(8):  # 4つのプレーヤー用に8列（各プレーヤーに2列）
        if i % 2 == 0:
            root.grid_columnconfigure(i, weight=1)  # プレーヤー列は均等に
        else:
            root.grid_columnconfigure(i, weight=0, minsize=80)  # ボリューム列は固定幅

    root.geometry("1280x400")
    app = VideoPlayerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()