python3 check_setup.py --out run1 --interval 0.2 --count 300 --prefix frame


python3 two_node_2.py --out run1 --count 300 --interval 1.0 --prefix pi1


python3 node_client.py --server-ip <DESKTOP_IP> --node-id node1 --interval 1.0
python3 node_client.py --server-ip <DESKTOP_IP> --node-id node2 --interval 1.0



python3 desktop_visualizer.py --port 5000 --node1-id node1 --node2-id node2


python3 node_capture_stream.py \
  --out session_node1 \
  --interval 1.0 \
  --count 1000 \
  --prefix n1 \
  --node-id node1 \
  --server-ip <DESKTOP_IP> \
  --server-port 5000

python3 two_node_1fps_networked_sync.py   --out session_node1   --interval 1.0   --count 50   --prefix n1   --node-id node1   --server-ip 10.0.0.135   --server-port 5000


python3 node_capture_stream.py \
  --out session_node2 \
  --interval 1.0 \
  --count 1000 \
  --prefix n2 \
  --node-id node2 \
  --server-ip <DESKTOP_IP> \
  --server-port 5000


python3 two_node_1fps_networked_sync.py   --out session_node2   --interval 1.0   --count 50   --prefix n2   --node-id node2   --server-ip 10.0.0.135   --server-port 5000

python3 desktop_viewer_3d.py --port 5000 --node1-id node1 --node2-id node2


sudo timedatectl set-ntp true
timedatectl status


python3 nodes_ntp.py\
  --out session_node1 \
  --node-id node1 \
  --server-ip 10.0.0.135 \
  --server-port 5000 \
  --slow-interval 1.0 \
  --fast-interval 0.1 \
  --warmup-frames 15 \
  --imu-threshold 3.0 \
  --uwb-window 5.0 \
  --max-frames 0   # 0 = run until Ctrl+C



python3 nodes_ntp.py\
  --out session_node2 \
  --node-id node2 \
  --server-ip 10.0.0.135 \
  --server-port 5000 \
  --slow-interval 1.0 \
  --fast-interval 0.1 \
  --warmup-frames 15 \
  --imu-threshold 3.0 \
  --uwb-window 5.0 \
  --max-frames 0   # 0 = run until Ctrl+C
