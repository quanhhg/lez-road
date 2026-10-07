[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.295414,105.339324,21.340697,105.387650)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.295414,105.339324,21.340697,105.387650);
  node["barrier"](21.295414,105.339324,21.340697,105.387650);
);
(._; >>;);
out meta;
out count;
