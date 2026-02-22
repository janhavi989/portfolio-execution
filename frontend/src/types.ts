export interface User {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface BrokerSession {
  id: string;
  broker: string;
  client_id: string | null;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
}

export interface BrokerCredentials {
  broker: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  api_key: string | null;
  api_secret: string | null;
  client_id: string | null;
  access_token: string | null;
  refresh_token: string | null;
  request_token: string | null;
  totp_secret: string | null;
  password: string | null;
  expires_at: string | null;
}

export interface FundsSegment {
  enabled: boolean;
  net: number;
  cash: number;
  opening_balance: number;
  live_balance: number;
  collateral: number;
  debits: number;
  span: number;
  exposure: number;
}

export interface BrokerFunds {
  broker: string;
  paper_trading: boolean;
  equity: FundsSegment | null;
  commodity: FundsSegment | null;
}

export interface Holding {
  symbol: string;
  exchange: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  pnl: number;
}

export interface TargetHolding {
  symbol: string;
  exchange: string;
  quantity: number;
  instruction?: string;
}

export interface DeltaOrder {
  symbol: string;
  exchange: string;
  order_type: "BUY" | "SELL";
  instruction_type: string;
  quantity: number;
  current_qty: number;
  target_qty: number;
}

export interface Order {
  id: string;
  symbol: string;
  exchange: string;
  order_type: string;
  instruction_type: string;
  quantity: number;
  order_status: string;
  filled_quantity: number;
  avg_fill_price: number | null;
  broker_order_id: string | null;
  error_message: string | null;
  placed_at: string | null;
  filled_at: string | null;
}

export interface ExecutionBatch {
  id: string;
  broker: string;
  execution_type: string;
  status: string;
  target_portfolio: { holdings: TargetHolding[] };
  current_holdings: Holding[];
  delta_orders: DeltaOrder[];
  summary: {
    total_orders?: number;
    filled?: number;
    failed?: number;
    partial?: number;
    paper_trading?: boolean;
    message?: string;
    error?: string;
  };
  orders: Order[];
  created_at: string;
  completed_at: string | null;
}

export interface WsMessage {
  type: "CONNECTED" | "ORDER_PROGRESS" | "EXECUTION_COMPLETE";
  data: Record<string, unknown>;
}

export type BrokerName = "zerodha" | "fyers" | "angelone" | "upstox" | "groww";

export const BROKER_DISPLAY: Record<BrokerName, string> = {
  zerodha: "Zerodha",
  fyers: "Fyers",
  angelone: "AngelOne",
  upstox: "Upstox",
  groww: "Groww",
};

export const BROKER_COLORS: Record<BrokerName, string> = {
  zerodha: "#387ED1",
  fyers: "#F04E23",
  angelone: "#E63329",
  upstox: "#6B4FBB",
  groww: "#00D09C",
};


