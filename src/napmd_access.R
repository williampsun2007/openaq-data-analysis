# Install required package
install.packages("RPostgreSQL")

# Connect to database
require("RPostgreSQL")
drv <- dbDriver("PostgreSQL")
postgres_pwd <- Sys.getenv("NAPMD_PASSWORD")
ch <- dbConnect(drv, dbname = "postgis_car",
                host = Sys.getenv("NAPMD_HOST"), port = 5432,
                user = Sys.getenv("NAPMD_USER"), password = postgres_pwd)
remove(postgres_pwd)

# Pull station locations for each state
df.locations <- dbGetQuery(ch, "SELECT station_id, station, state, lat, lon FROM air_pollution_monitors.ap_monitor_locations_act;")
df.nsw <- dbGetQuery(ch, "SELECT * FROM air_pollution_monitors.ap_monitor_locations_nsw;")
df.vic <- dbGetQuery(ch, "SELECT * FROM air_pollution_monitors.ap_monitor_locations_vic;")
df.tas <- dbGetQuery(ch, "SELECT * FROM air_pollution_monitors.ap_monitor_locations_tas;")
df.wa <- dbGetQuery(ch, "SELECT * FROM air_pollution_monitors.ap_monitor_locations_wa;")
df.sa <- dbGetQuery(ch, "SELECT * FROM air_pollution_monitors.ap_monitor_locations_sa;")
df.qld <- dbGetQuery(ch, "SELECT * FROM air_pollution_monitors.ap_monitor_locations_qld;")
df.nt <- dbGetQuery(ch, "SELECT * FROM air_pollution_monitors.ap_monitor_locations_nt;")

# Combine all location stations into one table
cols_needed <- c("station_id", "station", "state", "lat", "lon")
df.locations.all <- rbind(
  df.locations[, cols_needed],
  df.nsw[, cols_needed],
  df.vic[, cols_needed],
  df.tas[, cols_needed],
  df.wa[, cols_needed],
  df.sa[, cols_needed],
  df.qld[, cols_needed],
  df.nt[, cols_needed]
)
write.csv(df.locations.all, "data/australia_napmd_station_locations.csv", row.names = FALSE)

# After running xu_to_napmd_matches.csv, pull actual PM2.5/O3 data for the matched stations
df.ids <- read.csv("data/xu_to_napmd_matches.csv")
id_list <- paste(df.ids$napmd_station_id, collapse = ", ")
query <- paste0("SELECT * FROM air_pollution_monitors.ap_monitor_data_master
                 WHERE station_id IN (", id_list, ")
                 AND variable IN ('pm25', 'o3')
                 AND date BETWEEN '2019-01-01' AND '2019-02-10';")
df.australia_data <- dbGetQuery(ch, query)
write.csv(df.australia_data, "data/australia_napmd_data_2019window.csv", row.names = FALSE)