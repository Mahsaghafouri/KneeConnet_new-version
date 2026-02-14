flowchart TB
  A[Entry Point\nif __name__ == '__main__'] --> B[QApplication\n+ Apply ModernTheme\n+ App Icon]
  B --> C[TermsDialog\n(Terms of Service)]
  C -->|Accepted| D[MainWindow\n(KneeConnect UI)]
  C -->|Rejected| Z[Exit]

  subgraph MainWindow["MainWindow (Main Camera + Instruction Video + Controls)"]
    D --> D1[Vision Camera Panel\n(feed_label + cam toggle)]
    D --> D2[Instruction Panel\n(QVideoWidget + QMediaPlayer)]
    D --> D3[Control Bar\nSelect Exercise / Start / Stop\nShow Progress / Patient Admin]

    D --> T1[VisionCameraThread\n(from vision_thread.py)\naka VisionCameraThread]
    T1 -->|signal: change_pixmap_signal(QImage)| D4[update_image(qt_img)\n-> feed_label.setPixmap]

    D3 -->|Select Exercise| E1[select_exercise()]
    E1 -->|video_map| D2
    E1 -->|set item| T1
    E1 -->|enable processing| T1

    D3 -->|START/PAUSE| E2[toggle_start()]
    E2 -->|process_enabled True/False| T1

    D3 -->|STOP| E3[stop_process()]
    E3 -->|process_enabled False| T1
    E3 -->|media_player.stop()| D2

    D3 -->|Patient Admin| E4[open_patient_admin()]
    E4 --> PD[PatientDashboard\n(QDialog)]
    E4 -->|stop thread temporarily| T1
    PD -->|on close| E4R[resume camera thread]
  end

  subgraph PatientDashboard["PatientDashboard (Sidebar + Stacked Pages)"]
    PD --> S1[ListWidget Menu]
    PD --> S2[QStackedWidget Pages]
    S2 --> P1[MergedPatientForm\n(load/save JSON)]
    S2 --> P2[SetupPage\n(SimpleCameraThread + record slots)]
    S2 --> P3[ExerciseForm\n(schedule table)]
    S2 --> P4[Consent Page]
    S2 --> P5[GenericFormWidget\n(Progress Report)]

    P2 --> ST[SimpleCameraThread\n(webcam only)]
    ST -->|signal: change_pixmap_signal(QImage)| P2W[CameraDisplayWidget.set_image()]
  end
