ip route del default
ip route add default via 10.0.10.254

# streamlit run /app/front.py
streamlit run /app/front.py --server.port=8501 --server.address=0.0.0.0