import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# Page configuration
st.set_page_config(
    page_title="BTC Short Straddle Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
BASE_URL = "https://api.india.delta.exchange"
UNDERLYING = "BTC"
STRIKE_1 = 75000
STRIKE_2 = 80000

# Initialize session state for historical data
if 'premium_history' not in st.session_state:
    st.session_state.premium_history = []
if 'last_update' not in st.session_state:
    st.session_state.last_update = None

# Helper Functions
def get_nearest_weekly_expiry():
    """Get the nearest Friday expiry date in DD-MM-YYYY format"""
    today = datetime.now()
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0 and today.hour >= 15:  # If it's Friday after 3 PM, get next Friday
        days_until_friday = 7
    if days_until_friday == 0:  # If today is Friday before 3 PM
        days_until_friday = 0
    
    nearest_friday = today + timedelta(days=days_until_friday)
    return nearest_friday.strftime("%d-%m-%Y")

def fetch_option_chain(expiry_date):
    """Fetch option chain data from Delta Exchange"""
    try:
        url = f"{BASE_URL}/v2/tickers"
        params = {
            "contract_types": "call_options,put_options",
            "underlying_asset_symbols": UNDERLYING,
            "expiry_date": expiry_date
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('success') and 'result' in data:
            return data['result']
        return None
    except Exception as e:
        st.error(f"API Error: {str(e)}")
        return None

def get_option_price(option_chain, strike, option_type):
    """Extract mark price for a specific strike and option type"""
    if not option_chain:
        return None
    
    for option in option_chain:
        if (float(option.get('strike_price', 0)) == strike and 
            option.get('symbol', '').startswith(option_type)):
            return float(option.get('mark_price', 0))
    return None

def get_spot_price(option_chain):
    """Extract BTC spot price from option chain data"""
    if option_chain and len(option_chain) > 0:
        return float(option_chain[0].get('spot_price', 0))
    return None

def calculate_straddle_premiums(option_chain, strike_1, strike_2):
    """Calculate individual and combined straddle premiums"""
    call_1 = get_option_price(option_chain, strike_1, 'C')
    put_1 = get_option_price(option_chain, strike_1, 'P')
    call_2 = get_option_price(option_chain, strike_2, 'C')
    put_2 = get_option_price(option_chain, strike_2, 'P')
    spot = get_spot_price(option_chain)
    
    if None in [call_1, put_1, call_2, put_2]:
        return None
    
    straddle_a = call_1 + put_1
    straddle_b = call_2 + put_2
    combined = straddle_a + straddle_b
    
    return {
        'straddle_a': straddle_a,
        'straddle_b': straddle_b,
        'combined': combined,
        'spot': spot,
        'call_1': call_1,
        'put_1': put_1,
        'call_2': call_2,
        'put_2': put_2
    }

def determine_trend(history, window=5):
    """Determine if premium is rising, falling, or flat"""
    if len(history) < window:
        return "Insufficient Data"
    
    recent = [h['combined'] for h in history[-window:]]
    first_half_avg = sum(recent[:len(recent)//2]) / (len(recent)//2)
    second_half_avg = sum(recent[len(recent)//2:]) / (len(recent) - len(recent)//2)
    
    change_pct = ((second_half_avg - first_half_avg) / first_half_avg) * 100
    
    if change_pct > 1:
        return "Rising ⬆️"
    elif change_pct < -1:
        return "Falling ⬇️"
    else:
        return "Flat ➡️"

def determine_risk_status(history, current_premium):
    """Determine risk status based on premium behavior"""
    if len(history) < 10:
        return "Neutral", "⚪", "Collecting initial data..."
    
    premiums = [h['combined'] for h in history]
    avg_premium = sum(premiums) / len(premiums)
    min_premium = min(premiums)
    max_premium = max(premiums)
    
    # Calculate volatility
    volatility = (max_premium - min_premium) / avg_premium * 100
    
    # Calculate recent change
    recent_change_pct = ((current_premium - premiums[-10]) / premiums[-10]) * 100
    
    # Risk logic for SHORT straddle
    # Premium decreasing = Good (theta decay)
    # Premium increasing = Bad (volatility expansion)
    
    if recent_change_pct < -5:  # Premium dropped significantly
        return "Safe", "🟢", "Premium compressing - Theta decay working well"
    elif recent_change_pct > 10:  # Premium increased significantly
        return "Risky", "🔴", "Premium expanding - Volatility risk increasing"
    elif volatility > 15:  # High volatility in premium
        return "Risky", "🔴", "High premium volatility detected"
    elif recent_change_pct > 5:  # Moderate premium increase
        return "Neutral", "🟡", "Slight premium expansion - Monitor closely"
    else:
        return "Safe", "🟢", "Premium stable - Position behaving as expected"

# Main Dashboard
def main():
    st.title("📊 BTC Short Straddle Monitor")
    st.markdown("**Strategy:** Combined Short Straddle (Income/Theta Decay)")
    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        expiry_date = get_nearest_weekly_expiry()
        st.info(f"**Expiry:** {expiry_date}")
        st.info(f"**Strike 1:** ${STRIKE_1:,}")
        st.info(f"**Strike 2:** ${STRIKE_2:,}")
        
        st.markdown("---")
        st.markdown("### 📖 Strategy Guide")
        st.markdown("""
        **Short Straddle:**
        - Sell Call + Put at each strike
        - Collect premium upfront
        - Profit from theta decay
        - Risk: Large BTC moves
        
        **Indicators:**
        - 🟢 Safe: Premium compressing
        - 🟡 Neutral: Stable premium
        - 🔴 Risky: Premium expanding
        """)
        
        auto_refresh = st.checkbox("Auto-refresh (30s)", value=True)
        
        if st.button("🗑️ Clear History"):
            st.session_state.premium_history = []
            st.rerun()
    
    # Fetch data
    with st.spinner("Fetching option chain data..."):
        option_chain = fetch_option_chain(expiry_date)
        
        if option_chain:
            premiums = calculate_straddle_premiums(option_chain, STRIKE_1, STRIKE_2)
            
            if premiums:
                # Update history
                timestamp = datetime.now()
                st.session_state.premium_history.append({
                    'timestamp': timestamp,
                    'combined': premiums['combined'],
                    'straddle_a': premiums['straddle_a'],
                    'straddle_b': premiums['straddle_b'],
                    'spot': premiums['spot']
                })
                
                # Keep only last 500 data points
                if len(st.session_state.premium_history) > 500:
                    st.session_state.premium_history = st.session_state.premium_history[-500:]
                
                st.session_state.last_update = timestamp
                
                # Determine trend and risk
                trend = determine_trend(st.session_state.premium_history)
                risk_status, risk_icon, risk_message = determine_risk_status(
                    st.session_state.premium_history, 
                    premiums['combined']
                )
                
                # Main metrics
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        "Combined Premium",
                        f"${premiums['combined']:,.2f}",
                        delta=None
                    )
                
                with col2:
                    st.metric(
                        "BTC Spot",
                        f"${premiums['spot']:,.2f}",
                        delta=None
                    )
                
                with col3:
                    st.metric("Trend", trend)
                
                with col4:
                    st.metric("Risk Status", f"{risk_icon} {risk_status}")
                
                # Risk message
                if risk_status == "Safe":
                    st.success(f"✅ {risk_message}")
                elif risk_status == "Risky":
                    st.error(f"⚠️ {risk_message}")
                else:
                    st.warning(f"ℹ️ {risk_message}")
                
                # Detailed breakdown
                st.markdown("---")
                st.subheader("📋 Position Breakdown")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown(f"""
                    **Straddle A (Strike: ${STRIKE_1:,})**
                    - Call Premium: ${premiums['call_1']:,.2f}
                    - Put Premium: ${premiums['put_1']:,.2f}
                    - **Total: ${premiums['straddle_a']:,.2f}**
                    """)
                
                with col2:
                    st.markdown(f"""
                    **Straddle B (Strike: ${STRIKE_2:,})**
                    - Call Premium: ${premiums['call_2']:,.2f}
                    - Put Premium: ${premiums['put_2']:,.2f}
                    - **Total: ${premiums['straddle_b']:,.2f}**
                    """)
                
                # Chart
                st.markdown("---")
                st.subheader("📈 Combined Premium History")
                
                if len(st.session_state.premium_history) > 1:
                    df = pd.DataFrame(st.session_state.premium_history)
                    
                    fig = go.Figure()
                    
                    # Combined premium line
                    fig.add_trace(go.Scatter(
                        x=df['timestamp'],
                        y=df['combined'],
                        mode='lines+markers',
                        name='Combined Premium',
                        line=dict(color='#1f77b4', width=3),
                        marker=dict(size=6)
                    ))
                    
                    # Add average line
                    avg_premium = df['combined'].mean()
                    fig.add_hline(
                        y=avg_premium,
                        line_dash="dash",
                        line_color="gray",
                        annotation_text=f"Avg: ${avg_premium:,.2f}",
                        annotation_position="right"
                    )
                    
                    fig.update_layout(
                        title="Combined Straddle Premium Over Time",
                        xaxis_title="Time",
                        yaxis_title="Premium ($)",
                        hovermode='x unified',
                        height=500,
                        template="plotly_white"
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Additional chart: Individual straddles
                    fig2 = go.Figure()
                    
                    fig2.add_trace(go.Scatter(
                        x=df['timestamp'],
                        y=df['straddle_a'],
                        mode='lines',
                        name=f'Straddle A (${STRIKE_1:,})',
                        line=dict(color='#ff7f0e', width=2)
                    ))
                    
                    fig2.add_trace(go.Scatter(
                        x=df['timestamp'],
                        y=df['straddle_b'],
                        mode='lines',
                        name=f'Straddle B (${STRIKE_2:,})',
                        line=dict(color='#2ca02c', width=2)
                    ))
                    
                    fig2.update_layout(
                        title="Individual Straddle Premiums",
                        xaxis_title="Time",
                        yaxis_title="Premium ($)",
                        hovermode='x unified',
                        height=400,
                        template="plotly_white"
                    )
                    
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.info("Collecting data... Chart will appear after multiple updates.")
                
                # Last update timestamp
                st.caption(f"Last updated: {st.session_state.last_update.strftime('%Y-%m-%d %H:%M:%S')}")
                
            else:
                st.error("❌ Could not calculate premiums. Check if strikes are available.")
        else:
            st.error("❌ Failed to fetch option chain data.")
    
    # Auto-refresh logic
    if auto_refresh:
        time.sleep(30)
        st.rerun()

if __name__ == "__main__":
    main()
