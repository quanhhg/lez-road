[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.616012,105.817661,20.661425,105.865903)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.616012,105.817661,20.661425,105.865903);
  node["barrier"](20.616012,105.817661,20.661425,105.865903);
);
(._; >>;);
out meta;
out count;
